import os
from contextlib import contextmanager
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.db.connection import get_connection


@pytest.mark.skipif(os.getenv("EVIDENCERAG_INTEGRATION") != "1", reason="Requires PostgreSQL")
def test_reader_annotations_round_trip_and_anchor_validation(monkeypatch):
    with get_connection() as conn, conn.transaction(force_rollback=True):
        @contextmanager
        def scoped_connection():
            with conn.transaction():
                yield conn

        monkeypatch.setattr("app.api.reader_annotations.get_connection", scoped_connection)
        papers = [
            conn.execute("""
                INSERT INTO documents (title, filename, file_hash, page_count)
                VALUES ('Reader fixture', 'fixture.pdf', %s, 2) RETURNING id
            """, (uuid4().hex * 2,)).fetchone()[0]
            for _ in range(2)
        ]
        chunk = conn.execute("""
            INSERT INTO chunks (document_id, chunk_index, text, page_start, page_end, embedding_model, embedding_dimensions)
            VALUES (%s, 0, 'A 🧪 result.', 2, 2, 'fixture', 1) RETURNING id
        """, (papers[0],)).fetchone()[0]
        client = TestClient(app)
        paper, other = (f"/documents/{id_}" for id_ in papers)
        bookmark = paper + "/reader-bookmarks/2"
        annotations = paper + "/reader-annotations"
        selection = {"page": 2, "chunk_id": chunk, "start_offset": 2, "end_offset": 10, "note": ""}

        assert client.put(paper + "/reader-bookmarks/3").status_code == 422
        assert client.put(bookmark).status_code == 204
        assert client.put(bookmark).status_code == 204
        assert client.get(annotations, params={"page": 1}).json() == {"bookmarks": [2], "highlights": []}
        assert client.post(other + "/reader-highlights", json=selection).status_code == 404
        assert client.post(paper + "/reader-highlights", json={**selection, "page": 1}).status_code == 404
        for invalid in ({"end_offset": 100}, {"start_offset": 10}, {"note": "bad\x00"}, {"start_offset": 1, "end_offset": 2}):
            assert client.post(paper + "/reader-highlights", json={**selection, **invalid}).status_code == 422

        new = client.post(paper + "/reader-highlights", json=selection)
        assert new.status_code == 201
        assert new.json()["quote"] == "🧪 result"
        assert client.post(paper + "/reader-highlights", json=selection).status_code == 409
        path = f"/reader-highlights/{new.json()['id']}"
        note = {"note": "Review measurement protocol.", "revision": 1}
        assert client.patch(other + path, json=note).status_code == 404
        edited = client.patch(paper + path, json=note)
        assert edited.status_code == 200
        assert edited.json()["revision"] == 2
        assert client.patch(paper + path, json=note).status_code == 409
        assert client.delete(paper + path, params={"revision": 1}).status_code == 409

        conn.execute("DELETE FROM chunks WHERE id = %s", (chunk,))
        result = client.get(annotations, params={"page": 2}).json()
        assert result["highlights"] == [{**edited.json(), "chunk_id": None}]
        assert client.delete(paper + path, params={"revision": 2}).status_code == 204
        assert client.delete(bookmark).status_code == 204
        assert client.get(annotations, params={"page": 2}).json() == {"bookmarks": [], "highlights": []}
