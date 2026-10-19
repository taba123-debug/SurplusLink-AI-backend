# SurplusLink AI — complete demo backend

A Dockerized FastAPI/PostgreSQL modular monolith for a two-way packaged bakery surplus marketplace in Pakistan. It supports fictional organization identities, confirmed inventory, requirements, reviewable hosted AI extraction, deterministic matching, offers, inventory reservation, payment simulation, collection and simulated fee reporting.

Hosted AI now uses GroqCloud with GROQ_API_KEY. See [Groq migration verification](docs/GROQ_MIGRATION.md) for actual live test results and model-access errors.

## Start and inspect

Prerequisites: Docker Desktop (Linux containers), Compose and Git. No host Python, pip, PostgreSQL or model download is needed. Run from the repository directory:

```powershell
# New checkout only; preserve an existing .env and its password.
Copy-Item .env.example .env
# Edit POSTGRES_PASSWORD; optionally configure GROQ_API_KEY and a verified AI_MODEL.
docker compose config --quiet
docker compose up -d --build
docker compose exec api alembic upgrade head
docker compose exec api python -m app.seed
docker compose ps
docker compose logs --tail=100 api
docker compose exec api pytest -q
```

Swagger: [localhost:8000/docs](http://localhost:8000/docs). API base: `http://localhost:8000/api/v1`. Liveness: `/health` (no database access). Readiness: `/ready` (`SELECT 1`). API source is bind-mounted and Uvicorn reloads Python changes; dependency/Dockerfile changes require rebuilding. Environment changes require recreating the API container.

Beekeeper PostgreSQL connection: host `127.0.0.1`, port **15432**, database/user `surpluslink`, password from `.env`, SSL off locally. Refresh `public` → Tables. API containers connect through `db:5432`, not the desktop port. Both published ports bind to loopback only.

```powershell
docker compose exec api alembic current
docker compose exec api alembic check
docker compose down
```

`down` retains named volumes. **`down -v` deletes records; do not use it to repair passwords or migrations.** Changing POSTGRES_PASSWORD in `.env` does not change an initialized PostgreSQL role password. To change that password, run `docker compose exec db psql -U surpluslink -d surpluslink`, use `\password surpluslink`, then `\q`, update `.env` to match, and run `docker compose up -d`.

## Complete HTTP demonstration

```powershell
docker compose exec api python -m app.demo
```

This creates fresh explicitly fictional records each run for Gulberg Packaged Foods and Johar Town Mini Mart. It creates a complete draft, publishes it, saves a buyer requirement, checks both matching directions, submits Rs. 120/unit, accepts, reserves 150 of 200 packs, creates a pending mock payment, simulates success, unlocks pickup details, confirms collection, and verifies dashboard revenue.

Expected result: COMPLETED; 150 sold, 0 reserved, 50 available; Rs. 18,360 buyer total, Rs. 17,640 seller net and **Rs. 720 simulated platform gross fees**. Repeated checkout reuses its payment. The default demo uses explicit structured fixture data and prints that AI was not invoked.

For the real AI path, first configure a working HF token/model, then run:

```powershell
docker compose up -d --force-recreate api
docker compose exec api python -m app.ai_smoke
docker compose exec api python -m app.demo --live-ai --confirm-demo-data
```

The live demo sends two real extraction requests and verifies expected fictional values before persistence. `--confirm-demo-data` explicitly confirms this known fixture scenario. Missing/invalid AI data stops the live demo; it never silently switches to manual or mocked extraction. Real-world UI users must review extracted values themselves before POST /lots or POST /requirements.

## Development identity and authorization

JWT/login is outside this project scope. Identity selection works only with **APP_ENV=development and DEMO_MODE=true**, and only for the five fictional seeded users/organizations. It is not production authentication and must never be used for real private supplier data.

```powershell
curl.exe http://localhost:8000/api/v1/demo/identities
```

Pick an identity's `user_id` and `organization_id`. Send both headers for private operations:

```text
X-Demo-User-ID: selected user_id
X-Demo-Org-ID: selected organization_id
```

The backend checks user, organization and active membership on every request. OWNER and MANAGER can mutate; STAFF can read organization-scoped details. The acting organization always comes from membership context, never a body field. Production or DEMO_MODE=false disables demo identity selection, mock payment mutation and the gated marketplace routes. Safe organization summaries remain public.

`/organizations/me` and `/lots/mine` are private; public DTOs exclude contacts, reserve prices, original seller text and pickup addresses. Buyer pickup access uses `/deals/{id}/pickup-details`, unlocked only for that deal's parties after successful simulated payment. Seller collection confirmation requires its OWNER/MANAGER role. The first seeded seller OWNER is the explicitly labelled platform-demo administrator; only that identity sees platform-wide simulated aggregates. Other identities see their own organization metrics.

## API and frontend integration

See [frontend integration guide](docs/FRONTEND.md) and the exported [OpenAPI contract](docs/openapi.json). Existing React sources are in a separate repository and were not available here; this schema is the authoritative contract for integration. CORS allows `http://localhost:5173` by default.

| Methods | Paths under `/api/v1` |
|---|---|
| GET | `/organizations`, `/organizations/{id}`, `/organizations/me` |
| GET | `/demo/identities`, `/demo/organizations`, `/demo/metadata` |
| POST, GET | `/lots` |
| GET | `/lots/{id}`, `/lots/mine` |
| PATCH | `/lots/{id}` |
| POST | `/lots/{id}/publish`, `/lots/{id}/pause` |
| POST, GET | `/requirements` |
| GET, PATCH | `/requirements/{id}` |
| POST | `/requirements/{id}/pause` |
| POST | `/ai/parse-lot`, `/ai/parse-requirement` |
| GET | `/requirements/{id}/matches`, `/lots/{id}/matching-buyers` (owner organization) |
| POST | `/lots/{id}/offers` |
| GET | `/offers`, `/offers/{id}` |
| POST | `/offers/{id}/respond`, `/offers/{id}/withdraw` |
| GET | `/deals`, `/deals/{id}`, `/deals/{id}/payment`, `/deals/{id}/pickup-details` |
| POST | `/deals/{id}/checkout`, `/deals/{id}/cancel`, `/deals/{id}/complete` |
| POST | `/payments/mock/{id}/succeed`, `/payments/mock/{id}/fail` |
| GET | `/dashboard/summary` |

Lists of lots, requirements, organizations, offers and deals support `limit` (1–100) and `offset`. Inventory creation requires all table-required fields, even for DRAFT. DRAFT can have unconfirmed flags; publication requires both confirmations. The compatible create default is ACTIVE, so clients wanting review-before-publication must explicitly send `status: "DRAFT"`. Editing stock with reservations/sales is blocked; use status actions to pause. Requirements with accepted deals cannot be edited. There are no destructive CRUD delete routes.

Allowed categories: `biscuits`, `bread`, `cakes`, `pastries`, `rusks`, `buns`. Units: `pack`, `carton`, `tray`, `piece`. Normalize common aliases/case; matching then uses exact category/unit/city. Storage: ambient/chilled/frozen. Only sealed packaging is accepted. Expiry is a date evaluated in Asia/Karachi; expiry-day stock is conservatively excluded.

## AI behavior and configuration

```env
AI_PROVIDER=groq
AI_BASE_URL=https://api.groq.com/openai/v1
AI_MODEL=llama-3.1-8b-instant
GROQ_API_KEY=your_backend_secret
AI_TIMEOUT_SECONDS=20
```

Never leave AI_MODEL as a placeholder. Availability depends on the router, provider and account; a catalog entry alone does not prove account access. The Groq key needs access to the configured model and available quota/credits. Keep it server-side and out of Git. No OpenAI-hosted model is implied by using its compatible Python SDK. SDK behavior follows [official OpenAI documentation](https://developers.openai.com/api/reference/python/resources/chat/subresources/completions/methods/create), with [Groq OpenAI compatibility](https://console.groq.com/docs/openai).

`description` is the primary parse input; the older `text` alias remains accepted. Both parse routes require demo identity headers. Example request:

```json
{
  "description": "200 sealed biscuit packs in Gulberg, Lahore, asking Rs. 140 per pack, minimum Rs. 110, expiry in 45 days.",
  "reference_date": "2026-10-18",
  "timezone": "Asia/Karachi"
}
```

Use the actual reference date in your UI. Relative expressions remain in `relative_expiry_expression` and `remaining_shelf_life_days`; an absolute date is derived only when both reference fields are valid and supplied. Output retains `data.quantity_total` for seller quantities to match the lot API. Money is extracted as decimal rupees and converted to integer paisa in Python. Unknown fields become null; ambiguous units become null. Exact supporting source quotes are required, but this is not proof of semantic correctness. Users must confirm safety/resale flags; AI cannot set them.

Responses include `provider`, `model`, `mode` (`live`/`mock`), `simulated`, `missing_fields`, `needs_review: true` and `persisted: false`. Review is always required, including for otherwise complete output. No LLM call persists or publishes inventory. Invalid output returns 502, provider timeout 504, and unavailable configuration/access/model/quota 503. Manual structured input remains usable when AI fails.

Explicit `AI_PROVIDER=mock` enables deterministic known test fixtures in development. It is always labelled mock/simulated, is not general-purpose extraction, and is never selected as a fallback. The optional live smoke command reports failure or missing credentials honestly. See [current completion report](PHASE3_8_REPORT.md) for actual live results.

## Inventory, transactions and revenue

```text
available = quantity_total - quantity_reserved - quantity_sold
```

All quantities are whole units. Submitting offers reserves nothing. Acceptance starts in the request transaction, locks the lot then offer, checks current expiry/stock/requirements and confidential seller reserve policy, reserves stock, snapshots financial totals, records an event and commits atomically. One offer can create one deal; the unique constraint and idempotent acceptance prevent duplicates. Row locking serializes competing acceptance and inventory transitions.

Checkout creates/reuses a PENDING MOCK payment. Explicit success marks it SUCCEEDED and the deal PAID; failure marks only that attempt FAILED and allows another checkout attempt. Duplicate callbacks are idempotent and do not duplicate events. A unique partial index prevents two successful payments per deal. Payment does not confirm collection.

Only the seller OWNER/MANAGER can complete a PAID deal. Completion moves reserved → sold and appends a collection event. Unpaid cancellation releases reservations and fails pending attempts. Paid cancellation is rejected because refunds are outside scope. Completed deals cannot be cancelled or completed twice. Payment is due one hour after deal creation, subject also to product expiry/pickup deadline. Run explicit unpaid cleanup when needed:

```powershell
docker compose exec api python -m app.services.deal_service
```

No queue or automatic background expiration is implied. Fee rates are 200 basis points per side. `fee = (subtotal_minor * 200 + 5000) // 10000` rounds nonnegative fees half up to a paisa; no floating point is used. SQL checks and a trigger protect monetary snapshots. Dashboard revenue counts only COMPLETED deals with successful MOCK payments, never merely accepted or paid transactions. All values are simulated; no real payment, transfer, escrow or earnings exist.

## Architecture and database ownership

The original factory, settings, session dependency and Docker setup are retained. Routes validate HTTP contracts; services own rules and transaction commits; named SQLAlchemy models own table mappings; Pydantic schemas control public/private output. Query helpers live in the catalog/dashboard services where reuse is useful; the repository package is available without adding unnecessary wrappers.

Key modules: `api/dependencies.py`, `core/security.py`, `services/catalog.py`, `services/marketplace.py`, `services/offer_service.py`, `services/deal_service.py`, `services/payment_service.py`, `services/dashboard_service.py`, `services/ai.py`, `services/ai_provider.py`, `services/ai_prompts.py`. API modules group organizations, existing marketplace operations, AI, offers, deals, payments and dashboard.

An SQLAlchemy engine owns pooled connections (two persistent plus one overflow). A request Session is a unit of work similar to passing a Prisma transaction client; querying starts a transaction, services commit it, and dependency teardown rolls unfinished work back. Repositories must not independently commit a multi-operation service transaction. NestJS typically injects constructor providers; FastAPI resolves request callables with Depends and handles yield cleanup.

The existing Alembic revision `4191df3243ce` remains unchanged in this extension. Existing columns and statuses support these features; no duplicate tables or unnecessary revision was created. Alembic tracks revision chains and can draft model/schema diffs; unlike typical Flyway SQL version files, generated Python migration operations still need review. Never use ORM create_all at startup. See [field definitions and Mermaid ER diagram](docs/DATABASE.md).

## Tests and maintenance

```powershell
docker compose exec api pytest -q
docker compose exec api alembic check
docker compose exec api python -m app.testing
```

Tests create/migrate `surpluslink_test` rather than resetting development data. Most use an outer rollback transaction and savepoints; real concurrency tests use independent connections and uniquely identified committed test records in that separate database. They cover membership/roles, CRUD/privacy, publication, extraction validation/errors, deterministic matches, fees, acceptance races, payment races/retries, cancellation, collection and simulated reporting. The existing Starlette HTTPX TestClient deprecation warning is recorded rather than hidden.

Dependency updates stay inside Docker and update the real lockfile:

```powershell
docker build --target tooling -t surpluslink-tooling .
docker run --rm --mount "type=bind,source=$($PWD.Path),target=/app" -w /app surpluslink-tooling uv lock --upgrade --default-index https://pypi.org/simple
docker compose up -d --build
docker compose exec api pytest -q
```

Dockerfile builds a Python 3.12 slim image with pinned uv, installing uv.lock before source for layer caching. Compose runs that image and PostgreSQL 17 on a private network, waits for the database healthcheck, and stores database records in a named volume. An image is the reusable package; a container is its running process/filesystem instance. Base tags remain patch-updatable rather than digest pinned.

Troubleshoot with `docker compose ps` and `docker compose logs --tail=100 db api`. If `/ready` fails, check role credentials and host `db`; pg_isready alone does not prove authentication. If AI returns model errors, replace placeholder model IDs and check the actual account/provider. If port 15432 is occupied, change only its host side and update Beekeeper. No local Python, PostgreSQL, Redis, Ollama or queues are required.

Production authentication, verification/food policy workflows, refunds, counteroffer audit revisions, operational deployment and real payments remain outside this demo. Do not use demo identities with real customer data.
