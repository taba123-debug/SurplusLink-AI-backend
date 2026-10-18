from fastapi import Query

from app.api.dependencies import get_db
from app.core.config import Settings


def test_url_handles_password_punctuation():
    settings = Settings(_env_file=None, postgres_password="p@ss:/?#$%word", database_url=None)
    assert settings.sqlalchemy_url.password == "p@ss:/?#$%word"
    assert settings.sqlalchemy_url.drivername == "postgresql+psycopg"


def test_session_is_closed_without_commit(app):
    from unittest.mock import MagicMock
    session = MagicMock()
    app.state.session_factory = MagicMock(return_value=session)
    request = MagicMock(app=app)
    dependency = get_db(request)
    assert next(dependency) is session.__enter__.return_value
    dependency.close()
    session.__exit__.assert_called_once()
    session.__enter__.return_value.commit.assert_not_called()


def test_validation_omits_input(app, client):
    @app.get("/test-validation")
    def validation(quantity: int = Query()):
        return {"quantity": quantity}
    response = client.get("/test-validation?quantity=sensitive-value")
    assert response.status_code == 422
    assert response.json()["error"]["details"] == [
        {"location": ["query", "quantity"], "type": "int_parsing"}
    ]
    assert "sensitive-value" not in response.text


def test_cors(client):
    response = client.options("/api/v1/ping", headers={
        "Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET",
    })
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
