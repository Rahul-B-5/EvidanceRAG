import os
from types import SimpleNamespace
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.retrieval import reembedding
from evaluation.database import isolated_database

pytestmark = pytest.mark.skipif(os.getenv("EVIDENCERAG_INTEGRATION") != "1", reason="Requires PostgreSQL")


@pytest.fixture
def indexed_paper(monkeypatch):
    with isolated_database() as (_, dsn):
        def connect():
            return psycopg.connect(dsn)

        monkeypatch.setattr(reembedding, "get_connection", connect)
        monkeypatch.setattr(reembedding, "get_settings", lambda: SimpleNamespace(
            embedding_model="updated-profile", embedding_dimensions=3,
        ))
        monkeypatch.setattr(reembedding, "BATCH_SIZE", 1)
        with connect() as conn:
            paper = conn.execute("""
                INSERT INTO documents(title,filename,file_hash,stored_path)
                VALUES ('Rebuild fixture','fixture.pdf',%s,'existing-source.pdf') RETURNING id
            """, (uuid4().hex * 2,)).fetchone()[0]
            for index in range(2):
                conn.execute("""
                    INSERT INTO chunks(document_id,chunk_index,text,page_start,page_end,embedding_model,embedding_dimensions,embedding)
                    VALUES (%s,%s,%s,%s,%s,'previous-profile',2,'[1,0]'::vector)
                """, (paper, index, f"Exact indexed text {index}.", index + 1, index + 1))
            conn.execute("""
                INSERT INTO saved_evidence(chunk_id,document_id,title,page_start,page_end,passage)
                SELECT id,document_id,'Rebuild fixture',page_start,page_end,text FROM chunks
                WHERE document_id=%s AND chunk_index=0
            """, (paper,))
        yield paper, connect


def chunk_rows(connect, paper):
    with connect() as conn:
        return conn.execute("""
            SELECT id,text,page_start,page_end,embedding_model,embedding_dimensions,embedding::text
            FROM chunks WHERE document_id=%s ORDER BY id
        """, (paper,)).fetchall()


def test_rebuild_swaps_one_profile_atomically_and_preserves_references(indexed_paper, monkeypatch):
    paper, connect = indexed_paper
    before = chunk_rows(connect, paper)

    def embed(texts):
        assert chunk_rows(connect, paper) == before
        return [[0, 1, 0] for _ in texts]

    monkeypatch.setattr(reembedding, "embed_documents", embed)
    client = TestClient(app)
    endpoint = f"/documents/{paper}/embeddings"
    stale = client.get(endpoint).json()
    assert stale["active_chunks"] == 0 and stale["total_chunks"] == 2
    accepted = client.post(endpoint + "/rebuild")
    assert accepted.status_code == 202
    complete = client.get(endpoint).json()
    assert complete["job"]["id"] == accepted.json()["id"]
    assert complete["job"]["status"] == "completed" and complete["active_chunks"] == 2
    after = chunk_rows(connect, paper)
    assert after == [(*row[:4], "updated-profile", 3, "[0,1,0]") for row in before]
    with connect() as conn:
        assert conn.execute("SELECT stored_path FROM documents WHERE id=%s", (paper,)).fetchone() == ("existing-source.pdf",)
        assert conn.execute("SELECT chunk_id FROM saved_evidence WHERE document_id=%s", (paper,)).fetchone() == (before[0][0],)


def test_failed_and_cancelled_rebuilds_preserve_all_previous_vectors(indexed_paper, monkeypatch):
    paper, connect = indexed_paper
    before = chunk_rows(connect, paper)
    client = TestClient(app)
    endpoint = f"/documents/{paper}/embeddings"
    job, _ = reembedding.queue_rebuild(paper)
    assert client.post(endpoint + "/rebuild").status_code == 409

    def embed(texts):
        if texts[0].endswith("1."):
            raise RuntimeError("Synthetic embedding failure.")
        return [[0, 1, 0]]

    monkeypatch.setattr(reembedding, "embed_documents", embed)
    reembedding.execute_rebuild(job["id"])
    failed = client.get(endpoint).json()["job"]
    assert failed["status"] == "failed" and failed["prepared_chunks"] == 1
    assert chunk_rows(connect, paper) == before
    replacement, _ = reembedding.queue_rebuild(paper)

    def stop_during_compute(_):
        assert client.post(endpoint + f"/rebuild/{replacement['id']}/cancel").status_code == 204
        return [[0, 1, 0]]

    monkeypatch.setattr(reembedding, "embed_documents", stop_during_compute)
    reembedding.execute_rebuild(replacement["id"])
    assert client.get(endpoint).json()["job"]["status"] == "cancelled"
    assert chunk_rows(connect, paper) == before

    expired, _ = reembedding.queue_rebuild(paper)
    with connect() as conn:
        conn.execute("UPDATE embedding_rebuilds SET lease_until=NOW()-INTERVAL '1 second' WHERE id=%s", (expired["id"],))
    assert client.get(endpoint).json()["job"]["status"] == "interrupted"
    reembedding.execute_rebuild(expired["id"])
    assert chunk_rows(connect, paper) == before
