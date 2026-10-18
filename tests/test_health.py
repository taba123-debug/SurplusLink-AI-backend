from app.api.dependencies import get_db


def test_health_is_independent_of_database(app, client):
    def unavailable():
        raise AssertionError("Health must not obtain a database session")
    app.dependency_overrides[get_db] = unavailable
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "surpluslink-api"}


def test_routing_and_docs(client):
    assert client.get("/api/v1/ping").json() == {"message": "SurplusLink API v1 is running"}
    assert client.get("/api/v1/ping").status_code == 200
    assert client.get("/missing").status_code == 404
    assert client.get("/openapi.json").status_code == 200
    assert client.get("/docs").status_code == 200
