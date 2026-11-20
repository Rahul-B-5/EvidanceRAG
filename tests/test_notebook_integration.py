import importlib
import os
from uuid import uuid4
from contextlib import nullcontext

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.db.connection import get_connection

pytestmark = pytest.mark.skipif(os.environ.get("EVIDENCERAG_INTEGRATION") != "1", reason="Requires local PostgreSQL")


def test_saved_evidence_keeps_note_and_authoritative_provenance(monkeypatch):
    module = importlib.import_module("app.api.saved_evidence")
    with get_connection() as conn, conn.transaction(force_rollback=True):
        doc_id = conn.execute("""
            INSERT INTO documents (title,filename,file_hash)
            VALUES ('Notebook fixture','fixture.pdf',%s) RETURNING id
        """, (uuid4().hex * 2,)).fetchone()[0]
        chunk_id = conn.execute("""
            INSERT INTO chunks (document_id,chunk_index,text,page_start,page_end,embedding_model,embedding_dimensions)
            VALUES (%s,0,'Synthetic calibration passage',2,3,'fixture',3) RETURNING id
        """, (doc_id,)).fetchone()[0]
        monkeypatch.setattr(module, "get_connection", lambda: nullcontext(conn))
        monkeypatch.setattr("app.api.main.get_connection", lambda: nullcontext(conn))
        client = TestClient(app)
        assert client.get(f"/documents/{doc_id}/passages", params={"page": 1}).json() == {"passages": []}
        assert client.get(f"/documents/{doc_id}/passages", params={"page": 3}).json()["passages"][0]["chunk_id"] == chunk_id
        assert client.put(f"/saved-evidence/{chunk_id}").status_code == 200
        assert client.patch(f"/saved-evidence/{chunk_id}", json={"note": "Check calibration sample."}).status_code == 200
        tags_url = f"/saved-evidence/{chunk_id}/tags"
        assert client.put(tags_url, json={"tags": [" Calibration ", "CALIBRATION", "check   sample"]}).json()["tags"] == [
            "calibration", "check sample",
        ]
        assert client.put(tags_url, json={"tags": ["two,tags"]}).status_code == 422
        assert client.put(tags_url, json={"tags": [""]}).status_code == 422
        assert client.put(tags_url, json={"tags": ["x"] * 13}).status_code == 422
        assert client.put(f"/saved-evidence/{chunk_id}").status_code == 200
        conn.execute("DELETE FROM documents WHERE id = %s", (doc_id,))
        item = next(p for p in client.get("/saved-evidence").json()["items"] if p["chunk_id"] == chunk_id)
        assert item["note"] == "Check calibration sample."
        assert item["tags"] == ["calibration", "check sample"]
        assert item["passage"] == "Synthetic calibration passage"
        assert item["page_start"] == 2
        assert item["source_exists"] is False
        assert client.put(tags_url, json={"tags": []}).json()["tags"] == []


def test_notebook_scope_limits_saved_passages_and_highlights(monkeypatch):
    with get_connection() as conn, conn.transaction(force_rollback=True):
        monkeypatch.setattr("app.api.saved_evidence.get_connection", lambda: nullcontext(conn))
        monkeypatch.setattr("app.api.reader_annotations.get_connection", lambda: nullcontext(conn))
        workspace = conn.execute("INSERT INTO workspaces(name) VALUES ('Notebook workspace') RETURNING id").fetchone()[0]
        collection = conn.execute("""
            INSERT INTO collections(workspace_id,name) VALUES (%s,'Notebook collection') RETURNING id
        """, (workspace,)).fetchone()[0]
        client = TestClient(app)
        papers = []
        for title in ("Allowed paper", "Other member", "Outside paper"):
            doc = conn.execute("""
                INSERT INTO documents(title,filename,file_hash) VALUES (%s,'fixture.pdf',%s) RETURNING id
            """, (title, uuid4().hex * 2)).fetchone()[0]
            chunk = conn.execute("""
                INSERT INTO chunks(document_id,chunk_index,text,page_start,page_end,embedding_model,embedding_dimensions)
                VALUES (%s,0,'Calibration passage',3,3,'fixture',3) RETURNING id
            """, (doc,)).fetchone()[0]
            papers.append((doc, chunk))
            assert client.put(f"/saved-evidence/{chunk}").status_code == 200
            assert client.post(f"/documents/{doc}/reader-highlights", json={
                "page": 3, "chunk_id": chunk, "start_offset": 0, "end_offset": 11, "note": "Repeat measurable test.",
            }).status_code == 201
        for doc, _ in papers[:2]:
            conn.execute("INSERT INTO workspace_documents(workspace_id,document_id) VALUES (%s,%s)", (workspace, doc))
        for doc, _ in (papers[0], papers[2]):
            conn.execute("INSERT INTO collection_documents(collection_id,document_id) VALUES (%s,%s)", (collection, doc))

        filters = {"workspace_id": workspace, "collection_id": collection}
        assert client.get("/saved-evidence", params={"collection_id": collection}).status_code == 404
        assert [row["document_id"] for row in client.get("/saved-evidence", params=filters).json()["items"]] == [papers[0][0]]
        highlights = "/saved-evidence/highlights"
        all_members = client.get(highlights, params={"workspace_id": workspace, "limit": 1}).json()
        assert all_members["has_more"]
        assert all_members["items"][0]["document_id"] == papers[0][0]
        assert client.get(highlights, params={**filters, "query": "impossible"}).json()["items"] == []
        items = client.get(highlights, params={**filters, "query": "repeat calibration"}).json()["items"]
        assert [(row["document_id"], row["page"], row["anchor_current"]) for row in items] == [(papers[0][0], 3, True)]
        conn.execute("UPDATE chunks SET text='Different source text' WHERE id=%s", (papers[0][1],))
        item = client.get(highlights, params=filters).json()["items"][0]
        assert not item["anchor_current"] and item["quote"] == "Calibration"
        conn.execute("DELETE FROM workspace_documents WHERE workspace_id=%s AND document_id=%s", (workspace,papers[0][0]))
        assert client.get(highlights, params=filters).json()["items"] == []
