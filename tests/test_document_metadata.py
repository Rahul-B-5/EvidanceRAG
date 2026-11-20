import os
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.db.connection import get_connection


def test_corrupt_pdf_upload_returns_422_and_does_not_publish_source(tmp_path, monkeypatch):
    settings = SimpleNamespace(upload_dir=tmp_path, max_upload_mb=1)
    conn = Mock()
    conn.transaction.side_effect = lambda: nullcontext()
    conn.execute.return_value.fetchone.return_value = None
    monkeypatch.setattr("app.api.main.get_settings", lambda: settings)
    monkeypatch.setattr("app.ingestion.pipeline.get_settings", lambda: settings)
    monkeypatch.setattr("app.ingestion.pipeline.get_connection", lambda: nullcontext(conn))
    response = TestClient(app).post("/documents", files={"file": ("damaged.pdf", b"not a PDF", "application/pdf")})
    assert response.status_code == 422
    assert list(tmp_path.rglob("*.pdf")) == []


@pytest.mark.skipif(os.getenv("EVIDENCERAG_INTEGRATION") != "1", reason="Requires PostgreSQL")
def test_metadata_revisions_preserve_source_and_chunks(monkeypatch):
    with get_connection() as conn, conn.transaction(force_rollback=True):
        monkeypatch.setattr("app.api.main.get_connection", lambda: nullcontext(conn))
        key = uuid4().hex * 2
        document = conn.execute("""
            INSERT INTO documents(title,filename,file_hash,stored_path) VALUES ('Fixture','fixture.pdf',%s,'fixture.pdf') RETURNING id
        """, (key,)).fetchone()[0]
        chunk = conn.execute("""
            INSERT INTO chunks(document_id,chunk_index,text,page_start,page_end,embedding_model,embedding_dimensions)
            VALUES (%s,0,'Indexed fixture content',2,2,'fixture',3) RETURNING id
        """, (document,)).fetchone()[0]
        client = TestClient(app)
        endpoint = f"/documents/{document}/metadata"
        payload = {"title": "Corrected title", "authors": ["Example, A."], "publication_year": 2025,
                   "venue": "Fixture Conference", "doi": "https://doi.org/10.1234/example",
                   "tags": ["Vision", "vision"], "metadata_revision": 1}
        assert client.patch(endpoint, json={**payload, "doi": "unsupported"}).status_code == 422
        response = client.patch(endpoint, json=payload)
        assert response.status_code == 200
        result = response.json()
        assert result["metadata_revision"] == 2 and result["doi"] == "10.1234/example"
        assert result["tags"] == ["vision"]
        assert client.patch(endpoint, json=payload).status_code == 409
        assert client.get(f"/documents/{document}/passages", params={"page": 2}).json()["passages"][0]["chunk_id"] == chunk
        assert conn.execute("SELECT trim(file_hash), stored_path FROM documents WHERE id=%s", (document,)).fetchone() == (key, "fixture.pdf")
