import importlib
import os
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from app.db.connection import get_connection
from app.db.repository import create_conversation

api = importlib.import_module("app.api.main")


@pytest.mark.skipif(os.environ.get("EVIDENCERAG_INTEGRATION") != "1", reason="Requires local PostgreSQL")
def test_exchange_is_atomic_and_failure_is_retryable(monkeypatch):
    with get_connection() as conn:
        with conn.transaction(force_rollback=True):
            conversation = create_conversation(conn, title="Temporary conversation test")
            cid = conversation["id"]
            @contextmanager
            def connection():
                with conn.transaction():
                    yield conn
            monkeypatch.setattr(api, "get_connection", connection)
            monkeypatch.setattr(api, "retrieve_evidence", lambda *a, **k: {"context": "", "evidence": []})
            # Real no-evidence abstention: no provider needed.
            client = TestClient(api.app)
            result = client.post("/answers", json={"conversation_id": cid, "query": "Test question"})
            assert result.status_code == 200 and result.json()["abstained"]
            assert conn.execute("SELECT count(*) FROM messages WHERE conversation_id=%s", (cid,)).fetchone()[0] == 2
            original_add = api.add_message
            def fail_assistant(*args, **kwargs):
                if kwargs["role"] == "assistant":
                    raise RuntimeError("Simulated persistence failure")
                return original_add(*args, **kwargs)
            monkeypatch.setattr(api, "add_message", fail_assistant)
            failing_client = TestClient(api.app, raise_server_exceptions=False)
            assert failing_client.post("/answers", json={"conversation_id": cid, "query": "Follow up"}).status_code == 500
            assert conn.execute("SELECT count(*) FROM messages WHERE conversation_id=%s", (cid,)).fetchone()[0] == 2
            monkeypatch.setattr(api, "add_message", original_add)
            assert client.post("/answers", json={"conversation_id": cid, "query": "Retry follow up"}).status_code == 200
            assert conn.execute("SELECT count(*) FROM messages WHERE conversation_id=%s", (cid,)).fetchone()[0] == 4
