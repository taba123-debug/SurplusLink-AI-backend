# Phase 3–8 implementation and verification report

## Outcome

The backend extension is implemented and verified through collection and simulated revenue. **75 tests passed**, none skipped; the existing Starlette HTTPX TestClient deprecation warning remains. The full manual-structured-data HTTP demonstration passed against the running PostgreSQL-backed API.

**The real-AI definition-of-done item is externally blocked:** actual Hugging Face requests returned HTTP 402 because the account has no remaining inference credits. A successful external model extraction is not claimed, and no mock fallback was used. This report does not label the complete real-AI E2E acceptance criterion achieved.

## Existing functionality retained

Inspection found the nine domain tables, initial revision `4191df3243ce`, 46 passing tests, the FastAPI factory, logging/settings/errors, Docker/Compose, PostgreSQL sessions, initial lot/requirement APIs, two-way matching, offer acceptance, fee snapshots and one-step mock payment.

The database contained real existing fictional demo records. No volume was deleted and no development data was reset. The completed migration was not rewritten. No duplicate tables or unnecessary new revision were generated: the existing columns/statuses support the required lifecycle. `alembic upgrade head` passed and `alembic check` reported no new operations.

## Added/extended modules

- `core/security.py`: fictional membership identity and owner/manager role policy.
- `api/dependencies.py`: seeded user/organization allowlists, active membership/user/organization checks and manager dependency, restricted to development DEMO_MODE.
- `services/catalog.py`: safe organization/listing queries, owned drafts, patches, publication/pause and edit-state validation.
- `services/ai_provider.py`, `services/ai_prompts.py`: typed provider protocol and separated extraction prompts; existing `services/ai.py` remains the adapter/extraction entry point to avoid duplicating working code.
- `services/offer_service.py`: authorized offer detail and withdrawal.
- `services/deal_service.py`: transactional cancellation, collection, pickup access and explicit unpaid cleanup.
- `services/payment_service.py`: pending checkout attempts, failure/retry, success and callback idempotency.
- `services/dashboard_service.py`: organization aggregates and restricted fictional platform-admin simulated totals.
- API modules: organizations, offers, deals, payments and dashboard extend the existing marketplace/AI routers.
- Pydantic contracts: explicit public/private lots and organizations; patches, payment lifecycle, match scoring, pickup access and typed dashboards.
- Seed upgrades only the known original fictional name placeholders to Gulberg Packaged Foods and Johar Town Mini Mart, preserving custom names, inventory and payment records.
- `app/demo.py`: repeatable complete manual or opt-in live-AI HTTP journey.
- Documentation: updated README, database reference, `docs/FRONTEND.md`, exported `docs/openapi.json` and this report. Earlier sprint reports remain historical.

No new dependency was required in this extension; the existing SDK dependency and uv.lock were retained and the Docker image rebuilt successfully.

## API coverage

Swagger/OpenAPI now publish **40 operations**, including foundation endpoints. New/extended operations include:

```text
GET   /api/v1/organizations
GET   /api/v1/organizations/{id}
GET   /api/v1/organizations/me
GET   /api/v1/demo/identities
GET   /api/v1/demo/metadata
GET   /api/v1/lots/mine
PATCH /api/v1/lots/{id}
POST  /api/v1/lots/{id}/publish
POST  /api/v1/lots/{id}/pause
PATCH /api/v1/requirements/{id}
POST  /api/v1/requirements/{id}/pause
GET   /api/v1/offers/{id}
POST  /api/v1/offers/{id}/withdraw
GET   /api/v1/deals
POST  /api/v1/deals/{id}/cancel
POST  /api/v1/deals/{id}/complete
GET   /api/v1/deals/{id}/pickup-details
GET   /api/v1/deals/{id}/payment
POST  /api/v1/payments/mock/{id}/succeed
POST  /api/v1/payments/mock/{id}/fail
GET   /api/v1/dashboard/summary
```

Existing lot/requirement creation and reads, both parse routes, both match directions, offer submission/list/respond, deal detail and checkout remain available, with strengthened access/state contracts.

## Authorization and confidentiality

Private operations require both X-Demo-User-ID and X-Demo-Org-ID, membership/role validation and active records. Only five fictional seeded identities can be selected, and only in APP_ENV=development with DEMO_MODE=true. OWNER/MANAGER can mutate; STAFF is read-only. Arbitrary body organization IDs are forbidden. This remains deliberately local/demo identity selection, not secure production authentication.

Public responses omit seller reserve prices, pickup addresses, original seller input and confidential organization contacts. Owned listings and organization details use explicit private DTOs. Reverse matching requires the lot seller; requirement matches require its owner organization. Pickup details unlock only for a paid/completed deal's participants. Collection requires the seller owner/manager. Platform-wide demo metrics are restricted to the first seeded seller OWNER; other identities receive null for that section.

## AI provider, model and actual result

Configured path: Hugging Face Inference Providers, OpenAI-compatible SDK, `https://router.huggingface.co/v1`. Candidate model: `Qwen/Qwen3-4B-Instruct-2507`, previously confirmed in the live router catalog. Its availability to this account was not established by a successful completion.

Actual attempts:

1. No token initially: smoke command explicitly reported NOT RUN.
2. After the user configured credentials, the environment's `AI_MODEL=your_verified_model_id` returned HTTP 400/model_not_found.
3. A request using the catalog-listed Qwen model returned HTTP 402.
4. A minimal diagnostic request confirmed the sanitized provider message: **“You have no remaining credits.”**

The `.env` model placeholder was replaced with the Qwen candidate, preserving the user's token/password. The image/container was rebuilt with current settings. No credential is printed or committed. No further hosted requests are retried while quota is exhausted. Manual structured input works independently.

Extraction now accepts `description` and the legacy `text` alias, validates length, requires strict JSON/Pydantic output, normalizes allowed categories/units and decimal money, preserves relative expiry expressions, and derives an absolute expiry only from an explicitly supplied valid reference date/timezone. Missing/unsupported values are null and review is always required. Output has explicit live/mock mode and never persists automatically. Live errors are controlled/sanitized; unsupported access/model/quota returns 503, timeout 504 and invalid output 502. Mock mode must be selected explicitly and is never a fallback.

After inference credits/account access are available, run:

```powershell
docker compose up -d --force-recreate api
docker compose exec api python -m app.services.ai
docker compose exec api python -m app.demo --live-ai --confirm-demo-data
```

The last command requires both extraction calls to succeed and match the known fictional scenario before saving. It has not succeeded in this session due to the external credit restriction.

## Matching and inventory concurrency

Matching remains deterministic SQL/Python. Hard filters enforce exact normalized category/unit/city, different organizations, active/confirmed/sealed inventory, available stock, minimum order, shelf life and valid expiry/pickup. Disabled organizations are excluded. DIRECT scores 100 and fits asking-price total plus estimated 2% buyer fee; NEGOTIABLE scores 80 and fits non-price criteria while exceeding budget. Ineligible candidates are excluded. Subtotal, estimated fee/total, grounded reasons and safe summaries are returned. Hidden reserve prices never influence buyer-facing classifications.

Every state transition affecting stock takes PostgreSQL row locks in lot-first order, then offer/deal/payment as needed. Acceptance re-reads state/expiry, checks current stock and confidential seller price policy, reserves quantity, creates one immutable deal and event, and commits together. Linked requirements are revalidated before acceptance. Repeated acceptance reuses the deal. Database checks and unique offer/deal references backstop the service rules.

Unpaid cancellation releases reserved stock and fails pending attempts. Payment success retains reservations. Seller collection moves reserved stock to sold exactly once and records the event. The explicit development cleanup command cancels unpaid deals older than one hour or past product/collection eligibility; no automatic queue is implied.

## Financial snapshots and mock payment states

All calculations use integer paisa and 200 basis points per side, half-up rounding:

```text
subtotal = quantity * agreed_unit_price_minor
fee = (subtotal * 200 + 5000) // 10000
buyer_total = subtotal + buyer_fee
seller_net = subtotal - seller_fee
```

SQL checks and an existing trigger protect snapshots from rewriting. Frontend totals are not authoritative. The example 150 × Rs. 120 yields Rs. 18,000 subtotal, Rs. 360 each fee, Rs. 18,360 buyer total and Rs. 17,640 seller net.

Checkout creates/reuses PENDING, rather than the earlier automatic-success behavior. Success sets SUCCEEDED/PAID and unlocks private pickup details. Failure sets FAILED without marking paid; a new attempt is allowed. Duplicate same-result callbacks do not duplicate events; conflicting terminal results return 409. A unique partial index prevents multiple successful payments per deal. Completed/cancelled transitions are explicit; paid cancellation is rejected because refunds are not implemented.

Dashboard revenue counts only COMPLETED deals with successful MOCK payments. All totals are marked simulated. No payment transfer, escrow or real earnings occurred.

## Tests and verification

Checkpoints executed inside Docker:

- Baseline: 46 passed.
- CRUD/access checkpoint: 23 relevant tests passed.
- AI validation/errors checkpoint: 20 relevant tests passed.
- Matching checkpoint: 17 relevant tests passed.
- Offers/reservation checkpoint: 18 relevant tests passed.
- Payment/collection/concurrency checkpoint: 7 relevant tests passed.
- First full regression: 73 passed.
- Final full regression, adding cancellation-versus-success and duplicate-collection races: **75 passed, 1 warning, none skipped**.

Tests use the separate migrated `surpluslink_test` database, rollback isolation for ordinary tests and unique committed records for real concurrent connection races. Development data is never reset by tests. Provider errors are mocked in automated tests; actual failed live requests are reported separately above.

Final live checks: PostgreSQL healthy, API running; `/health`, `/ready`, `/docs`, `/openapi.json` and `/api/v1/demo/identities` returned HTTP 200. The OpenAPI JSON artifact parsed successfully. `alembic upgrade head` and `alembic check` passed. Compose validation and whitespace checks passed; .env remains Git-ignored.

## Commands executed

```powershell
docker compose exec api pytest -q
docker compose exec api alembic current
docker compose exec api alembic check
docker compose exec -T db psql -U surpluslink -d surpluslink -c '\dt'
docker compose exec api pytest -q tests/test_access_and_catalog.py tests/test_marketplace.py tests/test_health.py
docker compose exec api pytest -q tests/test_ai.py tests/test_extraction_extended.py
docker compose exec api pytest -q tests/test_matching_extended.py tests/test_marketplace.py
docker compose exec api pytest -q tests/test_offer_lifecycle.py tests/test_concurrency.py tests/test_marketplace.py
docker compose exec api pytest -q tests/test_deals_and_payments.py tests/test_concurrency.py
docker compose exec api python -m app.seed
docker compose run --rm --no-deps -T api python -m app.services.ai
docker compose run --rm --no-deps -T -e AI_MODEL=Qwen/Qwen3-4B-Instruct-2507 api python -m app.services.ai
docker compose up -d --build
docker compose exec api pytest -q
docker compose exec api alembic upgrade head
docker compose exec api alembic check
docker compose exec api python -m app.demo
docker compose ps
docker compose exec -T api python -c "import json; from app.main import create_app; print(json.dumps(create_app().openapi(),indent=2))" | Set-Content -Encoding utf8 docs/openapi.json
git diff --check
git check-ignore .env
```

Additional Python/HTTPX probes checked live health/docs and operation count; minimal SDK diagnostic requests inspected only sanitized error bodies. No dependencies were installed on the host and no destructive migration or volume command ran.

## Exact demo walkthrough and frontend handoff

Run `docker compose exec api python -m app.demo` for a fresh, repeatable manual-data scenario. It creates a complete DRAFT, publishes it, saves the buyer requirement, confirms NEGOTIABLE matching in both directions, makes the offer, accepts/reserves, checks fee snapshots, creates PENDING checkout, succeeds the mock payment, reads authorized pickup details, confirms collection, verifies sold/available quantities and asserts the dashboard's simulated platform revenue increases by 72,000 paisa.

The final verified run returned COMPLETED, 150 sold, 50 available, buyer total 1,836,000 paisa, seller net 1,764,000 paisa and simulated gross fee delta 72,000 paisa. The output explicitly states AI was not invoked.

For React integration, use `docs/openapi.json` and `docs/FRONTEND.md`; fetch demo identities, send both identity headers, show extraction review forms, distinguish checkout/PENDING from payment/PAID and collection/COMPLETED, and use server monetary snapshots and dashboards. Frontend sources were not available in this repository, so UI integration itself was not performed.

## Remaining limitations

- Live AI success and the real-extraction E2E acceptance criterion await Hugging Face inference credits/access.
- Identity selection is a fictional local demonstration, not authentication suitable for real users.
- Complete drafts are supported; partially populated rows are not compatible with current non-null columns.
- No counteroffer audit model exists, so counteroffers are deferred.
- Refunds/paid cancellation, production verification/safety policies, operational deployment and real payment integration remain outside scope.
- Cleanup is explicit, not background scheduled. Test race records remain only in the isolated test database for inspection.
- The pre-existing TestClient/HTTPX deprecation warning remains; no warning was suppressed.

All containers are left running for review. No commits or pushes were made.
