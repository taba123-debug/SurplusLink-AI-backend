# SurplusLink AI backend — Phase 1

Dockerized foundation for a B2B surplus inventory marketplace in Pakistan. Phase 1 contains infrastructure only: no authentication, marketplace tables, AI calls, payments, or background services.

## Quick start (PowerShell)

Prerequisites: Git and running Docker Desktop with Linux containers and Compose. Local Python, pip, PostgreSQL, and uv are unnecessary.

```powershell
Copy-Item .env.example .env
# Edit .env and replace POSTGRES_PASSWORD with a private development password.
docker compose config --quiet
docker compose up -d --build
docker compose ps
docker compose logs --tail=100 api
Invoke-RestMethod http://localhost:8000/health
Invoke-RestMethod http://localhost:8000/ready
Invoke-RestMethod http://localhost:8000/api/v1/ping
docker compose exec api pytest -q
docker compose exec api alembic current
docker compose exec api alembic upgrade head
docker compose down
```

If `.env` already exists, preserve it instead of copying over it. This implementation session created an ignored `.env` with a random development password. Never commit it. View Swagger at [localhost:8000/docs](http://localhost:8000/docs) and the schema at [localhost:8000/openapi.json](http://localhost:8000/openapi.json).

`docker compose down` retains the named database volume. **`docker compose down -v` deletes database records** and should not be used casually.

## Architecture and important files

A modular monolith is one application and one deployment, with clear internal boundaries. The intended request flow is route → service → repository → SQLAlchemy session → PostgreSQL. Health routes are deliberately small and use no business services.

```text
app/
  main.py                  Application factory, lifecycle, CORS, health/readiness
  api/dependencies.py      Request-scoped database session dependency
  api/v1/router.py         Versioned API routes; currently ping only
  core/config.py           Typed environment settings and safe URL construction
  core/exceptions.py       Central API error envelope
  core/logging.py          Standard logging with credential-safe traceback formatting
  db/base.py               SQLAlchemy declarative metadata
  db/session.py            Engine and session factory
  schemas/health.py        Pydantic response contracts
  models/                  Future table mappings; currently empty
  repositories/            Future persistence operations; currently empty
  services/                Future business rules and transactions; currently empty
alembic/
  env.py                   Settings-driven online/offline migration runner
  script.py.mako           Revision template
  versions/                No business revisions yet
tests/                     HTTPX-backed TestClient endpoint tests
Dockerfile                 Reproducible development image
compose.yml                API and PostgreSQL services, network, volume
pyproject.toml             Dependency constraints and pytest configuration
uv.lock                    Exact resolved versions and package hashes
```

Stack: Python 3.12 slim, FastAPI, Uvicorn, SQLAlchemy 2, Psycopg 3 binary wheels, PostgreSQL 17, Pydantic 2, pydantic-settings, Alembic, pytest and HTTPX. uv 0.12.17 is pinned in Docker. `uv.lock` pins the complete Python dependency graph; base image tags receive upstream patches and are not digest pinned. No system compiler or extra service is installed. The connection pool allows two persistent connections and one overflow connection per API process.

## Settings and frontend connection

Compose reads `.env` for PostgreSQL variables and passes it to the API container. Settings are validated when the factory starts. Keep `POSTGRES_DB`, `POSTGRES_USER`, and `POSTGRES_PASSWORD` consistent; the API composes its URL using `URL.create`, so passwords containing URL punctuation are supported without manual encoding. Use single-quoted values in `.env` if your password contains `$` to avoid Compose interpolation.

An optional `DATABASE_URL` overrides the individual settings. It must use `postgresql+psycopg://` and URL-encoded credentials matching the database. Leave it unset for local development. `POSTGRES_HOST` defaults to `db` and `POSTGRES_PORT` to 5432. `.env.example` documents application name, development environment, API prefix, logging and CORS settings. `DEBUG=true` enables safe traceback locations in application logs; HTTP debug pages remain disabled.

Set comma-separated `CORS_ORIGINS` to exact frontend origins, for example `http://localhost:5173,http://localhost:3000`. React running in your browser calls `http://localhost:8000/api/v1/ping`. `db` is a Docker-only hostname, not the frontend API address. Only API port 8000 is published, bound to loopback; PostgreSQL has no host port.

`AI_PROVIDER`, `AI_BASE_URL`, `AI_MODEL`, `HF_TOKEN`, and `AI_TIMEOUT_SECONDS` are optional typed settings for later phases. No token is required and no provider is called.

## How startup and Docker work

An **image** is the packaged filesystem and startup instructions, like a reusable application build. A **container** is a running instance of that image with isolated processes and networking.

The Dockerfile describes building the API image: copy pinned uv, install the lockfile into `/opt/venv`, then copy source. Copying dependency files first lets Docker reuse installation layers when only application code changes. Compose describes running the API together with PostgreSQL, including configuration, networking, health checks, ports, and storage.

On startup PostgreSQL initializes an empty data volume once. Compose waits for `pg_isready`, then Uvicorn calls `create_app()`. The factory validates settings, configures logging, creates a lazy engine and session factory, and registers routes and exception handlers. Startup logs an event; it does not run queries, migrations, or `create_all()`. Shutdown disposes the engine pool.

The API connects to `db:5432` through the Compose network. The named `postgres_data` volume lives independently of containers, so replacing a container preserves records. Changing `POSTGRES_PASSWORD` after initialization does not change the password stored in PostgreSQL; change the database role password deliberately and then update `.env`.

Compose bind-mounts `app`, tests and Alembic sources. Uvicorn reloads when application Python files change. Dependencies stay outside those mounts in `/opt/venv`. Changing dependencies requires updating the lockfile and rebuilding; changing `.env` requires recreating the API container.

## Requests, dependency injection, and errors

Uvicorn accepts HTTP, FastAPI matches the URL and method, resolves dependencies, runs the handler, and validates its response model. An `APIRouter` groups routes, similar to a NestJS controller; `include_router(..., prefix="/api/v1")` mounts that group.

`Depends(get_db)` asks FastAPI to execute a callable for a request. The dependency yields a session and closes it after the handler. NestJS usually injects constructor dependencies from a provider container; FastAPI resolves callable dependencies in a request graph and supports teardown through `yield`. Tests replace dependencies using `app.dependency_overrides`.

Synchronous handlers run in FastAPI's worker thread pool, allowing ordinary synchronous database code without blocking the event loop.

| Endpoint | Meaning | Database required |
|---|---|---|
| `/health` | Process can respond | No |
| `/ready` | `SELECT 1` succeeds with configured credentials | Yes |
| `/api/v1/ping` | Versioned router is mounted | No |

Database failures return HTTP 503 with `{"error":{"code":"DATABASE_UNAVAILABLE","message":"Database connection is currently unavailable."}}`. Unknown routes return an error envelope with 404; validation failures return 422 without echoing submitted data; unexpected failures return a generic 500. Logs record failure events and exception types without SQL parameters, payloads, URLs or exception messages. Development traceback locations remain available. Uvicorn also provides request access logs; avoid putting secrets in URL query strings.

## Sessions and transactions: from Prisma to SQLAlchemy

An **engine** owns database connectivity and a pool, roughly the connection management part of a Prisma client. Creating it does not connect. A **Session** is a short-lived unit of work and identity map: it tracks loaded objects and pending changes for one request.

The first query normally begins a transaction automatically. Services decide when to commit. Closing a session rolls back unfinished work; the dependency never blindly commits. Unlike passing a Prisma transaction client into a callback, SQLAlchemy commonly passes the request session into repository methods and uses an explicit transaction block in the service:

```python
# Future service example only; no business models exist in Phase 1.
with session.begin():
    repository.create_listing(session, data)
    repository.record_inventory_change(session, data)
# Successful block commits both; failure rolls both back.
```

Start transaction blocks before other operations on that session. Alternatively call `session.commit()` deliberately and `session.rollback()` on failure. Repositories should not commit independent pieces of a service transaction.

## Migrations: from Flyway to Alembic

```powershell
docker compose exec api alembic current
docker compose exec api alembic upgrade head
# Phase 2 only, after approving the schema and importing models in app/models/__init__.py:
docker compose exec api alembic revision --autogenerate -m "create marketplace schema"
```

Both Flyway and Alembic track applied schema versions. Flyway commonly applies ordered SQL files; Alembic follows revision IDs linked by `down_revision`, usually executing Python `upgrade()`/`downgrade()` functions. Alembic autogenerate compares registered SQLAlchemy metadata to the live schema and drafts operations. Review generated revisions, especially renames, constraints and data changes; it cannot infer business intent.

There are no marketplace tables or placeholder revisions. `alembic current` has no revision to print in Phase 1. `upgrade head` can create Alembic's own version tracking table but no business schema. The first real migration belongs in Phase 2. Migrations are explicit commands and never run on API startup.

## Tests and verification

```powershell
docker compose exec api pytest -q
docker compose exec api alembic check
docker compose logs --tail=100 db api
```

The fast tests use HTTPX through FastAPI's TestClient, override database sessions, assert `SELECT 1`, simulate credential-bearing connection errors, and exercise routing and safe error handling. They do not need a live database. Real connectivity is separately verified through `/ready` against the running PostgreSQL container. `alembic check` verifies that metadata and schema have no pending differences without creating a revision.

To update dependencies using Docker only:

```powershell
docker build --target tooling -t surpluslink-tooling .
docker run --rm --mount "type=bind,source=$($PWD.Path),target=/app" -w /app surpluslink-tooling uv lock --upgrade --default-index https://pypi.org/simple
docker compose up -d --build
docker compose exec api pytest -q
```

Review and commit both `pyproject.toml` and `uv.lock` after dependency changes. Never replace the lockfile with a hand-written list.

## Troubleshooting

- Docker engine unavailable or permission denied: start Docker Desktop, select Linux containers, and ensure your account can access Docker. Codex may need approval to use the Docker named pipe.
- Port 8000 occupied: stop the conflicting process or change only the host side of the Compose port binding; update the frontend API URL.
- Database unhealthy: inspect `docker compose logs --tail=100 db` and confirm credentials against the initialized volume.
- API starts but `/ready` returns 503: inspect API and database logs, hostname and credentials. `pg_isready` alone does not prove API authentication works.
- Source changes do not reload on Windows: check bind mounts; if necessary set `WATCHFILES_FORCE_POLLING=true` and install Uvicorn's standard extras deliberately. The default minimal Uvicorn reloader polls Python files without extra dependencies.
- Low memory: run this single API process and database only; no AI downloads are involved. Adjust Docker Desktop's resource allocation to your machine and stop unrelated containers.

## Future phases and ownership

Routes handle HTTP contracts; services own business rules and transaction boundaries; repositories own persistence queries; models map tables; schemas validate API data. This keeps HTTP details out of business rules and avoids making database models the public API contract.

Next, approve organizations, users, inventory and requirement relationships before adding Phase 2 models and reviewed migrations. As features grow, group each marketplace domain into modules within this same application. Later an AI provider adapter can implement a service interface and use the optional settings, so ordinary marketplace APIs do not depend on provider-specific HTTP details. Authentication, listings, matching, offers, deals, checkout and AI remain outside Phase 1.
