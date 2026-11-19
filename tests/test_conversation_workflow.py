from contextlib import nullcontext
from unittest.mock import Mock
import importlib

from fastapi.testclient import TestClient
import pytest

api = importlib.import_module("app.api.main")
client = TestClient(api.app)


def setup_conversation(monkeypatch):
    monkeypatch.setattr(api, "get_connection", lambda: nullcontext(Mock()))
    monkeypatch.setattr(api, "get_conversation", lambda *a: {
        "id": 4, "document_id": 9, "workspace_id": None,
        "messages": [{"role": "user", "content": "Explain the model"}],
    })
    monkeypatch.setattr(api, "get_document", lambda *a: {"id": 9})


def test_provider_failure_writes_no_messages(monkeypatch):
    setup_conversation(monkeypatch)
    retrieve = Mock(return_value={"context": "evidence", "evidence": [{}]})
    monkeypatch.setattr(api, "retrieve_evidence", retrieve)
    monkeypatch.setattr(api, "generate_answer", Mock(side_effect=RuntimeError("Unavailable")))
    write = Mock()
    monkeypatch.setattr(api, "add_message", write)
    result = client.post("/answers", json={"query": "What about limitations?", "conversation_id": 4})
    assert result.status_code == 503
    write.assert_not_called()
    assert "Explain the model" in retrieve.call_args.args[0]
    assert retrieve.call_args.kwargs["document_id"] == 9


def test_conversation_cannot_expand_source_scope(monkeypatch):
    setup_conversation(monkeypatch)
    retrieve = Mock()
    monkeypatch.setattr(api, "retrieve_evidence", retrieve)
    response = client.post("/answers", json={"query": "Test", "conversation_id": 4, "document_id": 10})
    assert response.status_code == 409
    retrieve.assert_not_called()


@pytest.mark.parametrize("endpoint,payload", [
    ("/answers", {"query": "  "}),
    ("/conversations", {"title": "  "}),
])
def test_blank_text_rejected(endpoint, payload):
    assert client.post(endpoint, json=payload).status_code == 422


def test_missing_workspace_fails_before_retrieval(monkeypatch):
    monkeypatch.setattr(api, "get_connection", lambda: nullcontext(Mock()))
    monkeypatch.setattr(api, "get_workspace", lambda *a: None)
    retrieve = Mock()
    monkeypatch.setattr(api, "retrieve_evidence", retrieve)
    assert client.get("/search", params={"query": "test", "workspace_id": 9}).status_code == 404
    retrieve.assert_not_called()


def test_comparison_rejects_nonmember_before_retrieval(monkeypatch):
    monkeypatch.setattr(api, "get_connection", lambda: nullcontext(Mock()))
    monkeypatch.setattr(api, "get_workspace", lambda *a: {"documents": [{"id": 1}]})
    assert client.post("/comparisons", json={"document_ids": [1,2], "workspace_id": 9}).status_code == 422
