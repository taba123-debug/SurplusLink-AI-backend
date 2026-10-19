import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


@pytest.fixture(scope="session")
def db_engine():
    import subprocess
    import sys
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from app.core.config import get_settings
    from app.seed import seed
    subprocess.run([sys.executable, "-m", "app.testing"], check=True)
    url = get_settings().sqlalchemy_url.set(database="surpluslink_test")
    assert url.database == "surpluslink_test"
    engine = create_engine(url, pool_size=3, max_overflow=2)
    with Session(engine) as session, session.begin():
        seed(session)
    yield engine
    engine.dispose()


@pytest.fixture
def db(db_engine):
    from sqlalchemy.orm import Session
    with db_engine.connect() as connection:
        transaction = connection.begin()
        session = Session(bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False)
        yield session
        session.close()
        transaction.rollback()


@pytest.fixture
def market_client(app, client, db):
    from app.api.dependencies import get_db
    app.dependency_overrides[get_db] = lambda: db
    return client


@pytest.fixture
def app():
    return create_app(Settings(_env_file=None, postgres_password="test-password", debug=True))


@pytest.fixture
def client(app):
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client
    app.dependency_overrides.clear()
