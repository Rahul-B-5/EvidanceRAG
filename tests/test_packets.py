import os
from contextlib import nullcontext
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.db.connection import get_connection


@pytest.mark.skipif(os.getenv("EVIDENCERAG_INTEGRATION") != "1", reason="Requires PostgreSQL")
def test_packet_snapshots_revisions_drafting_and_scope(monkeypatch):
    with get_connection() as conn, conn.transaction(force_rollback=True):
        monkeypatch.setattr("app.api.main.get_connection", lambda: nullcontext(conn))
        monkeypatch.setattr("research.packets.get_connection", lambda: nullcontext(conn))
        workspace = conn.execute("INSERT INTO workspaces(name) VALUES ('Packet fixture') RETURNING id").fetchone()[0]
        doc = conn.execute("""
            INSERT INTO documents(title,filename,file_hash,authors,publication_year)
            VALUES ('Packet source','fixture.pdf',%s,ARRAY['Researcher, Example'],2025) RETURNING id
        """, (uuid4().hex * 2,)).fetchone()[0]
        chunk = conn.execute("""
            INSERT INTO chunks(document_id,chunk_index,text,page_start,page_end,embedding_model,embedding_dimensions)
            VALUES (%s,0,'F1 was 87 percent in the holdout.',4,4,'fixture',3) RETURNING id
        """, (doc,)).fetchone()[0]
        conn.execute("""
            INSERT INTO saved_evidence(chunk_id,document_id,title,page_start,page_end,passage,note)
            VALUES (%s,%s,'Packet source',4,4,'F1 was 87 percent in the holdout.','Original note.')
        """, (chunk, doc))
        request = {"workspace_id": workspace, "title": "Fixture packet", "chunk_ids": [chunk]}
        client = TestClient(app)
        assert client.post("/evidence-packets", json=request).status_code == 422
        conn.execute("INSERT INTO workspace_documents(workspace_id,document_id) VALUES (%s,%s)", (workspace, doc))
        response = client.post("/evidence-packets", json=request)
        assert response.status_code == 201
        packet = response.json()
        assert packet["items"][0]["authors"] == ["Researcher, Example"]
        url = f"/evidence-packets/{packet['id']}"
        assert all(p["id"] != packet["id"] for p in client.get("/evidence-packets").json()["packets"])
        conn.execute("UPDATE saved_evidence SET note='Later note' WHERE chunk_id=%s", (chunk,))
        edit = {"title": "Revised packet", "question": "Which metric changed?", "narrative": "Read [E1].", "revision": 1}
        updated = client.patch(url, json=edit)
        assert updated.status_code == 200 and updated.json()["revision"] == 2
        assert updated.json()["items"][0]["note"] == "Original note."
        assert client.patch(url, json=edit).status_code == 409
        generate = Mock(return_value={"answer": "The excerpt reports 87 percent [E1].", "abstained": False, "reason": None})
        monkeypatch.setattr("app.api.main.generate_answer", generate)
        assert client.post(url + "/draft").status_code == 200
        assert generate.call_args.args[2][0]["evidence_id"] == "E1"
        assert generate.call_args.args[2][0]["chunk_id"] == chunk
        assert client.get(url).json()["narrative"] == "Read [E1]."
        conn.execute("DELETE FROM workspace_documents WHERE workspace_id=%s AND document_id=%s", (workspace, doc))
        assert client.get(url).status_code == 404
        assert client.post(url + "/draft").status_code == 404
        assert client.get("/evidence-packets", params={"workspace_id": workspace}).json()["packets"] == []
