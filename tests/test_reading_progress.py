import os
from contextlib import contextmanager
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api import reading
from app.api.main import app
from app.db.connection import get_connection

pytestmark = pytest.mark.skipif(os.getenv("EVIDENCERAG_INTEGRATION") != "1", reason="Requires PostgreSQL")


def test_reading_state_is_independent_of_passages_and_retains_finished_status(monkeypatch):
    with get_connection() as conn, conn.transaction(force_rollback=True):
        @contextmanager
        def connection():
            with conn.transaction():
                yield conn

        monkeypatch.setattr(reading, "get_connection", connection)
        monkeypatch.setattr("app.api.main.get_connection", connection)
        modern = conn.execute("""
            INSERT INTO documents(title,filename,file_hash,page_count)
            VALUES ('Reading fixture','fixture.pdf',%s,5) RETURNING id
        """, (uuid4().hex * 2,)).fetchone()[0]
        legacy = conn.execute("""
            INSERT INTO documents(title,filename,file_hash)
            VALUES ('Legacy reading fixture','fixture.pdf',%s) RETURNING id
        """, (uuid4().hex * 2,)).fetchone()[0]
        original = conn.execute("""
            INSERT INTO chunks (document_id,chunk_index,text,page_start,page_end,embedding_model,embedding_dimensions)
            VALUES (%s,0,'Synthetic source',2,4,'fixture',3) RETURNING id,text
        """, (legacy,)).fetchone()
        client = TestClient(app)
        path = f"/documents/{modern}/reading"
        assert client.get(f"/documents/{modern}").json()["reading_status"] == "unread"
        for invalid in ({}, {"page": True}, {"status": "done"}, {"page": 6}):
            assert client.patch(path, json=invalid).status_code == 422
        visited = client.patch(path, json={"page": 5}).json()
        assert visited["last_read_page"] == 5 and visited["last_read_at"]
        assert visited["reading_status"] == "reading"
        completed = client.patch(path, json={"status": "finished"}).json()
        assert completed["reading_status"] == "finished"
        assert completed["last_read_at"] == visited["last_read_at"]
        assert client.patch(path, json={"page": 3}).json()["reading_status"] == "finished"
        assert client.get(f"/documents/{modern}").json()["last_read_page"] == 3
        assert client.patch(f"/documents/{legacy}/reading", json={"page": 1}).status_code == 422
        assert client.patch(f"/documents/{legacy}/reading", json={"page": 4}).json()["last_read_page"] == 4
        assert conn.execute("SELECT id,text FROM chunks WHERE document_id=%s", (legacy,)).fetchone() == original
