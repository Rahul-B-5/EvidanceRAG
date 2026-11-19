"""Opt-in PostgreSQL test. Every fixture mutation rolls back automatically."""
import json
import os
from contextlib import nullcontext

import pytest

from app.db.connection import get_connection
from app.retrieval import keyword, vector


@pytest.mark.skipif(os.environ.get("EVIDENCERAG_INTEGRATION") != "1", reason="Requires local PostgreSQL")
def test_workspace_never_returns_nonmember_chunks(monkeypatch):
    with get_connection() as conn:
        with conn.transaction(force_rollback=True):
            sample = conn.execute("""
                SELECT document_id, text, embedding::text, embedding_model, embedding_dimensions
                FROM chunks WHERE embedding IS NOT NULL ORDER BY id LIMIT 1
            """).fetchone()
            if sample is None:
                pytest.skip("Requires an indexed sample document")
            member = conn.execute("INSERT INTO workspaces(name) VALUES ('isolation test member') RETURNING id").fetchone()[0]
            empty = conn.execute("INSERT INTO workspaces(name) VALUES ('isolation test empty') RETURNING id").fetchone()[0]
            conn.execute("INSERT INTO workspace_documents(workspace_id,document_id) VALUES (%s,%s)", (member, sample[0]))
            from types import SimpleNamespace
            settings = SimpleNamespace(retrieval_top_k=100, embedding_model=sample[3], embedding_dimensions=sample[4])
            for module in (keyword, vector):
                monkeypatch.setattr(module, "get_connection", lambda: nullcontext(conn))
                monkeypatch.setattr(module, "get_settings", lambda: settings)
            # Reuse a stored vector: no model download, remote call or data rewrite.
            monkeypatch.setattr(vector, "embed_query", lambda _: json.loads(sample[2]))
            query = " OR ".join(sample[1].split()[:30])
            for search in (keyword.search_keyword, vector.search_vector):
                results = search(query, workspace_id=member)
                assert results
                assert {r["document_id"] for r in results} == {sample[0]}
                assert search(query, workspace_id=empty) == []
                assert search(query, workspace_id=member, document_id=9223372036854775807) == []
