# Phase 1 completion report

Verified on 18 October 2026. Phase 2 has not been started.

## Delivered

An application-factory FastAPI modular monolith, synchronous SQLAlchemy/Psycopg sessions, Pydantic settings and response schemas, safe error envelopes, standard logging, CORS, Alembic infrastructure, Docker hot reload, dependency locking and endpoint tests. No business models, authentication, AI calls or marketplace APIs were introduced.

Services: `api` serves HTTP on `127.0.0.1:8000`; `db` runs PostgreSQL 17 privately on the Compose network and persists data in `postgres_data`. The API pool permits two persistent connections plus one overflow connection.

## Created files

- `Dockerfile`, `compose.yml`, `.dockerignore`, `.gitignore`, `.env.example`
- `pyproject.toml`, generated `uv.lock`
- `app/main.py`
- `app/api/dependencies.py`, `app/api/v1/router.py`
- `app/core/config.py`, `app/core/logging.py`, `app/core/exceptions.py`
- `app/db/base.py`, `app/db/session.py`, `app/schemas/health.py`
- Package `__init__.py` files under app, api, api/v1, core, db, models, schemas, repositories and services
- `alembic.ini`, `alembic/env.py`, `alembic/script.py.mako`, `alembic/versions/.gitkeep`
- `tests/conftest.py`, `tests/test_health.py`, `tests/test_readiness.py`, `tests/test_foundation.py`
- `README.md`, `PHASE1_REPORT.md`
- Local ignored `.env`, initialized with a random development password; not included in the Docker image

The repository was initially empty apart from `.git`. No pre-existing source files were changed. Files are ready for review and have not been committed or pushed.

## Commands and outcomes

These are the build and verification commands executed from `C:\SurplusLink-AI-backend`:

```powershell
docker --version
docker compose version
docker info --format '{{.ServerVersion}}'
docker compose config --quiet
docker pull postgres:17
docker pull python:3.12-slim
docker build --target tooling -t surpluslink-tooling .
docker run --rm --mount "type=bind,source=C:\SurplusLink-AI-backend,target=/app" -w /app surpluslink-tooling uv lock --default-index https://pypi.org/simple
docker run --rm surpluslink-tooling python -c "import urllib.request; r=urllib.request.urlopen('https://pypi.org/simple/fastapi/', timeout=15); print('PyPI HTTP', r.status)"
docker compose up -d --build
docker compose ps
docker compose exec api pytest -q
docker compose exec api alembic current
docker compose exec api alembic upgrade head
docker compose exec api alembic check
docker compose logs --tail=100 api
docker compose exec db psql -U surpluslink -d surpluslink -c '\dt'
git check-ignore .env
git diff --check
git status --short
```

Live host HTTP verification:

```powershell
$ErrorActionPreference = 'Stop'
foreach ($path in @('/health','/ready','/api/v1/ping','/docs','/openapi.json')) {
    $r = Invoke-WebRequest -UseBasicParsing -Uri "http://localhost:8000$path"
    Write-Output "$path HTTP $($r.StatusCode)"
    if ($path -notin @('/docs','/openapi.json')) { Write-Output $r.Content }
}
```

Results:

| Check | Result |
|---|---|
| Compose configuration | Passed |
| Docker build and startup | Passed |
| PostgreSQL healthcheck | Healthy |
| API startup logs | Startup completed; no startup errors |
| `/health` | 200, expected JSON |
| `/ready` | 200, real PostgreSQL `SELECT 1` succeeded |
| `/api/v1/ping` | 200, expected JSON |
| `/docs`, `/openapi.json` | Both 200 |
| pytest | 9 passed, 1 upstream deprecation warning |
| Alembic current | Passed; no business revision exists |
| Alembic upgrade head | Passed |
| Alembic check | No new upgrade operations detected |
| Database tables | Only `alembic_version`; no marketplace tables |
| `.env` Git exclusion | Confirmed |

The initial sandboxed Docker and localhost HTTP commands were denied by environment access controls and succeeded after approved escalation. Two initial lock bootstrap commands failed and were replaced with the working tooling stage:

```powershell
docker run --rm --mount "type=bind,source=C:\SurplusLink-AI-backend,target=/app" -w /app ghcr.io/astral-sh/uv:0.12.17 uv lock --python 3.12 --default-index https://pypi.org/simple
# Failed: the image already uses uv as its entrypoint.
docker run --rm --mount "type=bind,source=C:\SurplusLink-AI-backend,target=/app" -w /app ghcr.io/astral-sh/uv:0.12.17 lock --python 3.12 --default-index https://pypi.org/simple
# Failed: this standalone image lacks the OS tools needed to discover Python.
```

## Remaining notes

No blocking issues remain. Starlette emits a deprecation warning about using HTTPX with TestClient and recommends HTTPX2. HTTPX was retained to match the requested testing stack; all tests pass. Revisit the transport when updating the testing stack. No tests were skipped.

Python dependency versions are fully locked. Docker base image tags remain patch-updatable rather than digest pinned. There is no production deployment setup in this phase.

Both containers are left running for review. Use `docker compose down` to stop them while preserving records. Never use `down -v` casually.

## Startup and next phase

Compose starts PostgreSQL and waits for its healthcheck. Uvicorn invokes `app.main:create_app`, settings are validated, the lazy engine/session factory is constructed, and routes, CORS and handlers are registered. Startup does not apply migrations or create tables. A readiness request obtains a session, executes `SELECT 1`, and closes the session.

Review the architecture and approve the marketplace database design next. Only then start Phase 2 models and the first reviewed business migration. See README for practical Docker/FastAPI explanations and NestJS/Prisma/Flyway comparisons.
