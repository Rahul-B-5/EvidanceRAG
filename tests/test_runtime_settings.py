from types import SimpleNamespace
from unittest.mock import Mock

from fastapi.testclient import TestClient
from psycopg import OperationalError

from app.api.main import app
from app.core.config import Settings


def test_diagnostics_keep_credentials_private_when_database_is_unavailable(monkeypatch):
    config = Settings(_env_file=None, generation_provider="openai", generation_model="fixture",
                      database_url="host=example.invalid dbname=fixture password=fixture-password",
                      generation_api_key="private fixture key", generation_base_url="", generation_timeout_seconds=90)
    monkeypatch.setattr("app.api.settings.get_settings", lambda: config)
    monkeypatch.setattr("app.api.settings.get_connection", Mock(side_effect=OperationalError("sensitive database detail")))
    response = TestClient(app).get("/settings")
    assert response.status_code == 200
    assert response.json()["generation"] == {
        "provider":"openai", "model":"fixture", "transport":"remote", "configured":True, "timeout_seconds":90,
    }
    assert not response.json()["database_connected"]
    assert response.json()["index"]["papers"] is None
    assert "example.invalid" not in response.text
    assert "private fixture key" not in response.text
    assert "fixture-password" not in repr(config)


def test_provider_check_uses_only_synthetic_json_and_redacts_failures(monkeypatch):
    config = Settings(_env_file=None, generation_provider="ollama", generation_model="fixture",
                      generation_timeout_seconds=90)
    monkeypatch.setattr("app.api.settings.get_settings", lambda: config)
    generate = Mock(return_value='{"ready":true}')
    provider = Mock(return_value=SimpleNamespace(generate_json=generate))
    monkeypatch.setattr("app.api.settings.get_generation_provider", provider)
    client = TestClient(app)
    assert client.post("/settings/test-provider").status_code == 422
    provider.assert_not_called()
    probe = client.post("/settings/test-provider", json={"synthetic":True})
    assert probe.status_code == 200 and probe.json()["elapsed_ms"] >= 0
    assert generate.call_args.kwargs["prompt"] == 'Reply with the JSON object {"ready": true}.'
    assert provider.call_args.args[0].generation_timeout_seconds == 15
    generate.side_effect = RuntimeError("raw private provider reply")
    unavailable = client.post("/settings/test-provider", json={"synthetic":True})
    assert unavailable.status_code == 503
    assert "raw private provider reply" not in unavailable.text
