"""Create/migrate a dedicated test database; never recreate development storage."""
from sqlalchemy import create_engine, text
from alembic import command
from alembic.config import Config

from app.core.config import get_settings

TEST_DATABASE = "surpluslink_test"


def prepare():
    import os
    settings = get_settings()
    if settings.sqlalchemy_url.database == TEST_DATABASE:
        raise RuntimeError("Run preparation with development settings, not test settings")
    engine = create_engine(settings.sqlalchemy_url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with engine.connect() as connection:
        if not connection.execute(text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": TEST_DATABASE}).scalar():
            connection.execute(text('CREATE DATABASE "surpluslink_test"'))
    engine.dispose()
    os.environ["DATABASE_URL"] = settings.sqlalchemy_url.set(database=TEST_DATABASE).render_as_string(hide_password=False)
    get_settings.cache_clear()
    command.upgrade(Config("alembic.ini"), "head")
    print("Dedicated test database migrated: surpluslink_test")


if __name__ == "__main__":
    prepare()
