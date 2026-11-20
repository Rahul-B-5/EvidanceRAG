import importlib
import os
from contextlib import contextmanager, nullcontext
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from app.db.connection import get_connection
from app.db.repository import create_conversation
from app.api.answer_stream import AnswerStreamCancelled
from app.generation import answerer
from app.retrieval import keyword, vector

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

            def cancel_after_insert(phase):
                count = conn.execute("SELECT count(*) FROM messages WHERE conversation_id=%s", (cid,)).fetchone()[0]
                if count == 6:
                    raise AnswerStreamCancelled

            with pytest.raises(AnswerStreamCancelled):
                api.answer_exchange(api.AnswerRequest(conversation_id=cid, query="Cancelled"), cancel_after_insert)
            assert conn.execute("SELECT count(*) FROM messages WHERE conversation_id=%s", (cid,)).fetchone()[0] == 4


@pytest.mark.skipif(os.environ.get("EVIDENCERAG_INTEGRATION") != "1", reason="Requires local PostgreSQL")
def test_selected_papers_scope_both_retrievers_and_saved_answer(monkeypatch):
    with get_connection() as conn, conn.transaction(force_rollback=True):
        @contextmanager
        def connection():
            with conn.transaction():
                yield conn

        monkeypatch.setattr(api, "get_connection", connection)
        settings = SimpleNamespace(retrieval_top_k=12, embedding_model="scope-fixture", embedding_dimensions=3)
        for module in (keyword, vector):
            monkeypatch.setattr(module, "get_connection", lambda: nullcontext(conn))
            monkeypatch.setattr(module, "get_settings", lambda: settings)
        monkeypatch.setattr(vector, "embed_query", lambda _: [1.0, 0.0, 0.0])
        monkeypatch.setattr(answerer, "get_generation_provider", lambda _: SimpleNamespace(
            generate_json=lambda **_: '{"answer":"Calibration findings [E1] [E2].","abstained":false,"reason":null}',
        ))

        workspace = conn.execute("INSERT INTO workspaces(name) VALUES ('Scope test') RETURNING id").fetchone()[0]
        fixture_ids = []
        phrase = "spectrocalibration"
        for suffix, embedding, member in [("A", "[0,1,0]", True), ("B", "[0,0,1]", True),
                                          ("C", "[1,0,0]", True), ("D", "[1,0,0]", False)]:
            title = f"Scope fixture {suffix}"
            doc = conn.execute(
                "INSERT INTO documents(title,filename,file_hash) VALUES (%s,%s,%s) RETURNING id",
                (title, f"fixture-{suffix}.pdf", uuid4().hex * 2),
            ).fetchone()[0]
            fixture_ids.append(doc)
            conn.execute("""INSERT INTO chunks (document_id, chunk_index, text, page_start, page_end,
                                embedding, embedding_model, embedding_dimensions)
                            VALUES (%s, 0, %s, 2, 2, %s::vector, %s, 3)""",
                         (doc, f"{phrase} result {suffix}.", embedding, settings.embedding_model))
            if member:
                conn.execute("INSERT INTO workspace_documents(workspace_id,document_id) VALUES (%s,%s)", (workspace, doc))

        first, second, other_member, outsider = fixture_ids
        chosen = [first, second]
        for search in (keyword.search_keyword, vector.search_vector):
            assert {hit["document_id"] for hit in search(phrase, top_k=2, document_ids=chosen, workspace_id=workspace)} == set(chosen)
        client = TestClient(api.app)
        keywords = client.get("/search", params=[("query", phrase), ("workspace_id", workspace),
                                *[("document_ids", id_) for id_ in chosen]])
        assert keywords.status_code == 200
        assert {item["document_id"] for item in keywords.json()["evidence"]} == set(chosen)
        payload = {"title": "Two selected papers", "document_ids": chosen, "workspace_id": workspace}
        assert client.post("/conversations", json={**payload, "document_ids": [first, outsider]}).status_code == 422
        assert client.post("/conversations", json={**payload, "document_ids": [first, first]}).status_code == 422
        assert client.post("/conversations", json={**payload, "document_id": first}).status_code == 422
        assert client.post("/conversations", json={**payload, "document_ids": []}).status_code == 422
        created = client.post("/conversations", json=payload)
        assert created.status_code == 201
        cid = created.json()["id"]
        assert client.get(f"/conversations/{cid}").json()["document_ids"] == chosen
        question = {"query": phrase, "conversation_id": cid}
        assert client.post("/answers", json={**question, "document_ids": [first, other_member]}).status_code == 409
        result = client.post("/answers", json=question)
        assert result.status_code == 200
        assert {item["document_id"] for item in result.json()["citations"]} == set(chosen)
        assert all(item["page_start"] == 2 for item in result.json()["citations"])

        def detach_during_generation(*args, **kwargs):
            conn.execute("DELETE FROM workspace_documents WHERE workspace_id=%s AND document_id=%s", (workspace, second))
            return {"answer": "Old scope.", "reason": None, "citations": []}

        monkeypatch.setattr(api, "generate_answer", detach_during_generation)
        assert client.post("/answers", json=question).status_code == 422
        assert client.post("/answers", json=question).status_code == 422
        assert len(client.get(f"/conversations/{cid}").json()["messages"]) == 2

        global_chat = client.post("/conversations", json={"title":"Sources survive deletion", "document_ids":[outsider]}).json()
        conn.execute("DELETE FROM documents WHERE id=%s", (outsider,))
        assert client.get(f"/conversations/{global_chat['id']}").json()["document_ids"] == [outsider]
        assert client.post("/answers", json={**question, "conversation_id":global_chat["id"]}).status_code == 404
