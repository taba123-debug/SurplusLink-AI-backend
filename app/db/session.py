from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings


def create_session_factory(settings: Settings):
    # Engine creation is lazy: connections open only when a query runs.
    engine = create_engine(
        settings.sqlalchemy_url, pool_pre_ping=True, pool_size=2, max_overflow=1,
        pool_timeout=5, connect_args={"connect_timeout": 3}, hide_parameters=True,
    )
    return engine, sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
