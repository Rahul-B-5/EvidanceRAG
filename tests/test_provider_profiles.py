import os
from contextlib import nullcontext
from pathlib import Path
from stat import S_IMODE

import pytest
import psycopg
from fastapi.testclient import TestClient

from app.api.main import app
from app.core.config import Settings
from app.generation.providers import get_answer_provider, get_extraction_provider
from evaluation.database import isolated_database

pytestmark = pytest.mark.skipif(os.getenv("EVIDENCERAG_INTEGRATION") != "1", reason="Requires PostgreSQL")


def test_profiles_encrypt_credentials_switch_live_and_isolate_tasks(monkeypatch, tmp_path: Path):
    defaults = Settings(_env_file=None, provider_key_path=tmp_path / "private" / "provider.key")
    with isolated_database() as (_, dsn), psycopg.connect(dsn) as conn, conn.transaction(force_rollback=True):
        for module in ("app.api.provider_profiles", "app.generation.profile_store"):
            monkeypatch.setattr(f"{module}.get_connection", lambda: nullcontext(conn))
        monkeypatch.setattr("app.api.provider_profiles.get_settings", lambda: defaults)
        client = TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 12345))
        endpoint = "/settings/providers/answer"
        draft = {"provider":"openai", "model":"fixture-model", "api_key":"synthetic-secret", "revision":0}
        result = client.put(endpoint, json=draft)
        assert result.status_code == 200
        assert result.json() == {"provider":"openai", "model":"fixture-model", "endpoint":"", "revision":1,
                                "has_key":True, "ollama_context_tokens":None}
        encrypted = conn.execute("SELECT credential FROM generation_profiles").fetchone()[0]
        assert b"synthetic-secret" not in encrypted
        assert S_IMODE(defaults.provider_key_path.stat().st_mode) == 0o600
        assert "synthetic-secret" not in client.get("/settings/providers").text
        assert "synthetic-secret" not in client.put(endpoint, json={**draft, "model":"invalid model"}).text
        assert get_answer_provider(defaults).model == "fixture-model"
        assert get_extraction_provider(defaults).model == "fixture-model"
        assert client.put(endpoint, json=draft).status_code == 409
        next_draft = {"provider":"openai", "model":"fixture-new", "revision":1}
        assert client.put(endpoint, json=next_draft).status_code == 200
        assert get_answer_provider(defaults).model == "fixture-new"
        assert client.put("/settings/providers/extraction", json={
            "provider":"ollama", "model":"fixture:local", "endpoint":"http://localhost:11434", "ollama_context_tokens":8192,
        }).status_code == 200
        assert get_extraction_provider(defaults).model == "fixture:local"
        assert get_extraction_provider(defaults).context_tokens == 8192
        assert client.get("/settings/providers").json()["extraction"]["ollama_context_tokens"] == 8192
        assert client.put(endpoint, json={**next_draft, "revision":2, "ollama_context_tokens":8192}).status_code == 422
        assert client.put("/settings/providers/extraction", json={
            "provider":"ollama", "model":"fixture:local", "revision":1, "ollama_context_tokens":90000,
        }).status_code == 422
        assert client.post("/settings/providers/ollama/models", json={"endpoint":"https://example.org"}).status_code == 422
        remote = TestClient(app, base_url="http://127.0.0.1", client=("192.0.2.10", 12345))
        assert remote.get("/settings/providers").status_code == 403
