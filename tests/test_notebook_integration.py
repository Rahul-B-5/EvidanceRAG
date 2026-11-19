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
        assert client.put(f"/saved-evidence/{chunk_id}").status_code == 200
        conn.execute("DELETE FROM documents WHERE id = %s", (doc_id,))
        item = next(p for p in client.get("/saved-evidence").json()["items"] if p["chunk_id"] == chunk_id)
        assert item["note"] == "Check calibration sample."
        assert item["passage"] == "Synthetic calibration passage"
        assert item["page_start"] == 2
        assert item["source_exists"] is False
