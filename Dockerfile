FROM ghcr.io/astral-sh/uv:0.12.17 AS uv
FROM python:3.12-slim AS tooling
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_PROJECT_ENVIRONMENT=/opt/venv PATH="/opt/venv/bin:$PATH"
WORKDIR /app
COPY --from=uv /uv /uvx /bin/
FROM tooling AS development
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --group dev --no-install-project
COPY app ./app
COPY alembic ./alembic
COPY tests ./tests
COPY alembic.ini ./
EXPOSE 8000
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
