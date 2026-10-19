# Final backend MVP sprint report

Historical snapshot of the earlier sprint. For the extended lifecycle, 75-test verification, current payment contract and live-provider credit restriction, see [Phase 3–8 report](PHASE3_8_REPORT.md).

## Starting point and delivered scope

The repository contained the working Phase 1 FastAPI factory, Docker/Compose, settings, logging/errors, SQLAlchemy base/session factory, Alembic runner and nine foundation tests. Live PostgreSQL contained only `alembic_version`; no domain revisions or tables existed. The current Beekeeper port mapping and password were preserved. No volume was deleted or development data reset.

Delivered in verified chunks:

1. Nine domain models, named constraints/indexes, reviewed migration and idempotent fictional Lahore seed: **20 tests passed** after fixing a seed helper argument collision caught by the first run.
2. Inventory/requirement APIs, explicit demo context, private-field filtering, two-way matching, offers, atomic acceptance, fees and simulated checkout: **34 tests passed**.
3. Hosted AI adapter, extraction schemas/prompts, safe failure handling, test-only mock, real PostgreSQL races and the HTTP demo: **46 tests passed** in the final run; none skipped. One existing Starlette TestClient/HTTPX deprecation warning remains.

## Database revision

`4191df3243ce` — `marketplace MVP schema`.

Before applying, the generated upgrade was inspected: only missing tables/indexes/constraints were added. Snapshot immutability and append-only history triggers were added deliberately. All nine requested domain tables now exist alongside Alembic's version table. `alembic current` reports head; `alembic check` reports no new upgrade operations.

Seed creates two fictional bakery organizations, three fictional retailers, five users/memberships, three lots and three requirements using deterministic UUIDs. Reruns preserve changed inventory and do not refresh original expiry dates. All contact emails use `example.invalid`.

## Code and endpoints

- Typed models: `app/models/marketplace.py`; declarative naming convention in `app/db/base.py`.
- HTTP contracts: `app/schemas/marketplace.py`, `app/schemas/extraction.py`.
- Thin routes: `app/api/v1/marketplace.py`, `app/api/v1/ai.py`, included in the existing router.
- Business transactions and deterministic matching: `app/services/marketplace.py`.
- One hosted provider adapter, two extraction prompts and clearly marked test mock: `app/services/ai.py`.
- Explicit commands: `app/seed.py`, `app/testing.py`, `app/demo.py`.
- Tests: `tests/test_database.py`, `tests/test_marketplace.py`, `tests/test_ai.py`, `tests/test_concurrency.py`; existing fixture extended with a dedicated migrated test database.
- Updated `pyproject.toml`/`uv.lock`, settings/example environment and README; [database reference](docs/DATABASE.md) includes field definitions and Mermaid ER diagram.

New operations under `/api/v1`:

```text
GET  /demo/organizations
POST /lots
GET  /lots
GET  /lots/{id}
POST /requirements
GET  /requirements
GET  /requirements/{id}
POST /ai/parse-lot
POST /ai/parse-requirement
GET  /requirements/{id}/matches
GET  /lots/{id}/matching-buyers
POST /lots/{id}/offers
GET  /offers
POST /offers/{id}/respond
GET  /deals/{id}
POST /deals/{id}/checkout
```

Together with `/health`, `/ready` and `/api/v1/ping`, Swagger publishes 19 operations. All original health/docs checks still return 200.

## Real versus mocked AI

The application uses the OpenAI Python SDK pointed to `https://router.huggingface.co/v1`, with explicit timeout and no automatic retries. The selected small model, `Qwen/Qwen3-4B-Instruct-2507`, was returned by the live HF `/v1/models` catalog (HTTP 200). The compatible interface was checked against [Hugging Face documentation](https://huggingface.co/docs/inference-providers/en/tasks/chat-completion) and [official OpenAI documentation](https://developers.openai.com/api/reference/python/resources/chat/subresources/completions/methods/create).

**No HF_TOKEN was configured.** The actual smoke command printed:

```text
LIVE_SMOKE_NOT_RUN: HF_TOKEN is not configured; no hosted inference was performed.
```

No successful real inference is claimed. Extraction validation, conversion, null handling and provider failures were tested using injected deterministic fixtures or mocked SDK transport responses. The application never silently switches to that mock. The HTTP marketplace demo uses explicit fictional data and does not claim to exercise AI.

To finish live AI verification, add HF_TOKEN with Inference Providers access to the existing `.env`, then run:

```powershell
docker compose up -d --force-recreate api
docker compose exec api python -m app.services.ai
```

That smoke test sends a fictional requirement to the hosted provider. Provider permissions, credits, JSON support and extraction quality remain unverified for this account. Model catalog presence does not prove successful inference access.

## Commands actually executed

All Python commands ran inside Docker:

```powershell
docker compose exec -T db psql -U surpluslink -d surpluslink -c '\dt'
docker compose exec api alembic current
docker compose exec api alembic revision --autogenerate -m "marketplace MVP schema"
# Reviewed the generated migration source before this command:
docker compose exec api alembic upgrade head
docker compose exec api alembic check
docker compose exec api python -m app.seed
docker compose exec api pytest -q
docker run --rm --mount "type=bind,source=C:\SurplusLink-AI-backend,target=/app" -w /app surpluslink-tooling uv lock --default-index https://pypi.org/simple
docker compose up -d --build
docker compose exec api pytest -q
docker compose exec api python -m app.services.ai
docker compose exec api python -m app.demo
docker compose exec api alembic current
docker compose exec api alembic check
docker compose logs --tail=35 api
```

Additional container Python/HTTPX probes checked the HF model catalog, live `/health`, `/ready`, `/docs`, `/openapi.json` and the number of published operations. PostgreSQL inspection confirmed all tables and five seeded organizations. The full live HTTP demo returned PAID with a single reused mock payment on duplicate checkout. Startup logs showed successful application startup and successful demo requests.

## Demonstration

The migration and seed are already applied, and both containers are running. Open [Swagger](http://localhost:8000/docs), or run:

```powershell
docker compose exec api python -m app.demo
```

It creates fresh demo stock each time and asserts the two matching directions and commission values. Actual verified output included:

```json
{
  "buyer_total_minor": 1836000,
  "seller_net_minor": 1764000,
  "platform_gross_fee_minor": 72000,
  "status": "PAID",
  "simulated": true,
  "duplicate_checkout_reused_payment": true
}
```

For a manual walkthrough, use README's curl/PowerShell examples or select the seeded seller/buyer using `X-Demo-Org-ID` in Swagger. Refresh Beekeeper at `127.0.0.1:15432`, database `surpluslink`, schema `public`.

## Limits and remaining work

- Demo organization selection is explicitly not authentication; new routes are gated by development/test environment and DEMO_MODE. No login, production authorization or deployment infrastructure was introduced.
- Live HF inference awaits credentials and a real smoke test. Extraction output always requires review, and exact evidence quotes alone cannot prove semantic correctness.
- Accepted deals reserve stock. Simulated payment marks PAID but does not mean pickup/completion; cancellation, automatic reservation expiry and refunds are not implemented. No money moves.
- Creation requires complete confirmed data; incomplete drafts, edits/deletes and counteroffers are outside the requested vertical slice.
- Matching is exact after normalization; no semantic matching, distance calculation, regulatory certification or analytics exists.
- Test races commit uniquely identified records only in `surpluslink_test`; development inventory is untouched by tests.
- Existing Starlette TestClient/HTTPX deprecation warning remains. All 46 tests pass.

No commits or pushes were made. Stop here for review and frontend integration.
