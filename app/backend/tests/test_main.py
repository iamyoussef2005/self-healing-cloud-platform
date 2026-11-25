import pytest
from fastapi.testclient import TestClient

from main import app


@pytest.fixture(autouse=True)
def reset_chaos_after_test():
    """Ensure simulated memory state is clean before and after each test."""
    with TestClient(app) as client:
        client.post("/chaos/reset")
        yield
        client.post("/chaos/reset")


def test_health_endpoint():
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_ready_endpoint():
    with TestClient(app) as client:
        response = client.get("/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert data["simulated_memory_mb"] == 0


def test_get_items():
    with TestClient(app) as client:
        response = client.get("/api/items")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == len(data["items"])
    assert data["count"] > 0
    first_item = data["items"][0]
    assert {"id", "name", "status", "region", "latency_ms"}.issubset(first_item.keys())


def test_chaos_memory_updates_gauge_and_resets():
    with TestClient(app) as client:
        chaos_resp = client.post("/chaos/memory?mb=16&allocate=false")
        assert chaos_resp.status_code == 200
        payload = chaos_resp.json()
        assert payload["status"] == "chaos_memory_triggered"
        assert payload["added_mb"] == 16
        assert payload["total_simulated_memory_mb"] == 16

        metrics_resp = client.get("/metrics")
        assert metrics_resp.status_code == 200
        assert "app_simulated_memory_mb 16.0" in metrics_resp.text

        reset_resp = client.post("/chaos/reset")
        assert reset_resp.status_code == 200
        assert reset_resp.json()["total_simulated_memory_mb"] == 0

        metrics_after = client.get("/metrics")
        assert "app_simulated_memory_mb 0.0" in metrics_after.text


def test_chaos_error_returns_500():
    with TestClient(app) as client:
        post_resp = client.post("/chaos/error")
        get_resp = client.get("/chaos/error")
    assert post_resp.status_code == 500
    assert get_resp.status_code == 500
    assert "Simulated HTTP 500" in post_resp.json()["detail"]


def test_metrics_exposes_http_instrumentation():
    with TestClient(app) as client:
        client.get("/api/items")
        response = client.get("/metrics")
    assert response.status_code == 200
    assert "app_simulated_memory_mb" in response.text
    assert "http_request_duration_seconds" in response.text or "http_requests_total" in response.text
