from unittest.mock import MagicMock

from sqlalchemy.exc import OperationalError

from app.api.dependencies import get_db


def test_ready(app, client):
    session = MagicMock()
    app.dependency_overrides[get_db] = lambda: session
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "connected"}
    assert str(session.execute.call_args.args[0]) == "SELECT 1"


def test_unavailable(app, client, capsys):
    session = MagicMock()
    session.execute.side_effect = OperationalError("SELECT 1", {}, Exception("postgresql://user:secret@db/password"))
    app.dependency_overrides[get_db] = lambda: session
    response = client.get("/ready")
    assert response.status_code == 503
    assert response.json() == {"error": {"code": "DATABASE_UNAVAILABLE", "message": "Database connection is currently unavailable."}}
    assert "secret" not in response.text
    assert "password" not in response.text
    assert "postgresql://" not in capsys.readouterr().err


def test_unexpected_error_is_safe(app, client):
    def broken():
        raise RuntimeError("sensitive-value")
    app.dependency_overrides[get_db] = broken
    response = client.get("/ready")
    assert response.status_code == 500
    assert "sensitive-value" not in response.text
