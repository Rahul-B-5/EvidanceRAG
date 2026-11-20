import os
from contextlib import contextmanager, nullcontext
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.db.connection import get_connection


@pytest.mark.skipif(os.getenv("EVIDENCERAG_INTEGRATION") != "1", reason="Requires PostgreSQL")
def test_collection_membership_and_detach_preserve_document(monkeypatch):
    with get_connection() as conn, conn.transaction(force_rollback=True):
        @contextmanager
        def scoped_connection():
            with conn.transaction():
                yield conn

        monkeypatch.setattr("app.api.main.get_connection", lambda: nullcontext(conn))
        monkeypatch.setattr("app.db.collections.get_connection", scoped_connection)
        workspace = conn.execute("INSERT INTO workspaces(name) VALUES ('Collection fixture') RETURNING id").fetchone()[0]
        paper = conn.execute("""
            INSERT INTO documents(title,filename,file_hash) VALUES ('Fixture','fixture.pdf',%s) RETURNING id
        """, (uuid4().hex * 2,)).fetchone()[0]
        client = TestClient(app)
        payload = {"workspace_id": workspace, "name": "Fixture collection"}
        new = client.post("/collections", json=payload)
        assert new.status_code == 201
        id_ = new.json()["id"]
        assert client.post("/collections", json={**payload, "name": "fixture COLLECTION"}).status_code == 409
        url = f"/collections/{id_}"
        link = url + f"/documents/{paper}"
        assert client.put(link).status_code == 422
        conn.execute("INSERT INTO workspace_documents(workspace_id,document_id) VALUES (%s,%s)", (workspace, paper))
        assert client.put(link).status_code == 204
        assert client.put(link).status_code == 204
        assert client.get(url).json()["document_ids"] == [paper]
        assert client.get("/collections", params={"workspace_id": workspace}).json()["collections"][0]["document_count"] == 1
        assert client.patch(url, json={"name": "Renamed group"}).json()["name"] == "Renamed group"
        conn.execute("DELETE FROM workspace_documents WHERE workspace_id=%s AND document_id=%s", (workspace, paper))
        assert client.get(url).json()["document_ids"] == []
        assert client.get("/collections", params={"workspace_id": workspace}).json()["collections"][0]["document_count"] == 0
        assert client.delete(link).status_code == 204
        assert client.get(f"/documents/{paper}").status_code == 200
