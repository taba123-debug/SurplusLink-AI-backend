import logging
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.api.v1.router import router
from app.core.config import Settings, get_settings
from app.core.exceptions import DatabaseUnavailable, register_exception_handlers
from app.core.logging import configure_logging
from app.db.session import create_session_factory
from app.schemas.health import ErrorResponse, HealthResponse, ReadinessResponse

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    engine, session_factory = create_session_factory(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logger.info("event=api_startup version=0.1.0")
        yield
        engine.dispose()

    # Framework debug is disabled so even development clients receive safe errors.
    app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.session_factory = session_factory
    app.add_middleware(CORSMiddleware, allow_origins=settings.allowed_origins,
                       allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
    register_exception_handlers(app)
    app.include_router(router, prefix=settings.api_v1_prefix)

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse()

    @app.get("/ready", response_model=ReadinessResponse, responses={503: {"model": ErrorResponse}})
    def ready(session: Annotated[Session, Depends(get_db)]) -> ReadinessResponse:
        try:
            session.execute(text("SELECT 1"))
        except SQLAlchemyError as exc:
            logger.error("event=database_readiness_failed exception_type=%s", type(exc).__name__,
                         exc_info=settings.debug)
            raise DatabaseUnavailable() from exc
        return ReadinessResponse()

    return app
