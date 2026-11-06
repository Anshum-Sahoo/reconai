from fastapi.testclient import TestClient


def test_health_check_api_v1(client: TestClient):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert data["version"] == "1.2.1"
    assert data["database"] == "connected"
    assert "ai_provider" in data
    # Verify no credentials leaked
    assert "password" not in data
    assert "secret" not in data
    assert "DEMO_ACCESS_PASSWORD" not in str(data)
    assert "JWT_SECRET" not in str(data)


def test_health_check_root(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ("ok", "degraded")
    assert data["database"] == "connected"
