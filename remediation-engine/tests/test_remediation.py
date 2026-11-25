from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from main import app


def _make_deployment(replicas: int):
    return SimpleNamespace(spec=SimpleNamespace(replicas=replicas))


def test_health_and_ready():
    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "healthy"}
        assert client.get("/ready").json() == {"status": "ready"}


def test_webhook_scales_up_on_high_memory(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    mock_apps_v1 = MagicMock()
    mock_apps_v1.read_namespaced_deployment.return_value = _make_deployment(2)

    payload = {
        "status": "firing",
        "alerts": [
            {
                "status": "firing",
                "labels": {
                    "alertname": "HighSimulatedMemory",
                    "namespace": "app",
                    "deployment": "demo-app-backend",
                    "severity": "critical",
                },
                "annotations": {"summary": "Simulated memory exceeded threshold"},
            }
        ],
    }

    with patch("main.get_apps_v1_client", return_value=mock_apps_v1):
        with TestClient(app) as client:
            resp = client.post("/webhook", json=payload)

    assert resp.status_code == 200
    result = resp.json()["results"][0]
    assert result["action"] == "scaled_up"
    assert result["previous_replicas"] == 2
    assert result["new_replicas"] == 3
    mock_apps_v1.patch_namespaced_deployment.assert_called_once_with(
        name="demo-app-backend",
        namespace="app",
        body={"spec": {"replicas": 3}},
    )


def test_webhook_respects_max_replica_limit(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    mock_apps_v1 = MagicMock()
    mock_apps_v1.read_namespaced_deployment.return_value = _make_deployment(5)

    payload = {
        "status": "firing",
        "alerts": [
            {
                "status": "firing",
                "labels": {
                    "alertname": "HighErrorRate",
                    "namespace": "app",
                    "deployment": "demo-app-backend",
                },
            }
        ],
    }

    with patch("main.get_apps_v1_client", return_value=mock_apps_v1):
        with TestClient(app) as client:
            resp = client.post("/webhook", json=payload)

    assert resp.status_code == 200
    result = resp.json()["results"][0]
    assert result["action"] == "scale_skipped_at_limit"
    assert result["new_replicas"] == 5
    mock_apps_v1.patch_namespaced_deployment.assert_not_called()


def test_webhook_restarts_on_crashloop(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    mock_apps_v1 = MagicMock()

    payload = {
        "status": "firing",
        "alerts": [
            {
                "status": "firing",
                "labels": {
                    "alertname": "PodCrashLooping",
                    "namespace": "app",
                    "deployment": "demo-app-backend",
                },
            }
        ],
    }

    with patch("main.get_apps_v1_client", return_value=mock_apps_v1):
        with TestClient(app) as client:
            resp = client.post("/webhook", json=payload)

    assert resp.status_code == 200
    result = resp.json()["results"][0]
    assert result["action"] == "rolling_restart"
    mock_apps_v1.patch_namespaced_deployment.assert_called_once()
