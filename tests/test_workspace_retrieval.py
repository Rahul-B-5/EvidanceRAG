import os
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest

from app.retrieval import keyword, vector
from app.db.connection import get_connection


@pytest.mark.parametrize("retriever", [keyword, vector])
def test_workspace_predicate_is_applied_before_limit(monkeypatch, retriever):
    conn = Mock()
    conn.execute.return_value.fetchall.return_value = []
    monkeypatch.setattr(retriever, "get_connection", lambda: nullcontext(conn))
    monkeypatch.setattr(retriever, "get_settings", lambda: SimpleNamespace(
        retrieval_top_k=5, embedding_dimensions=3, embedding_model="test",
    ))
    if retriever is vector:
        monkeypatch.setattr(vector, "embed_query", lambda _: [1., 0., 0.])
        monkeypatch.setattr(vector, "register_vector", lambda _: None)
    search = retriever.search_keyword if retriever is keyword else retriever.search_vector
    assert search("test", document_id=42, workspace_id=7) == []
    sql, params = conn.execute.call_args.args
    assert sql.index("wd.workspace_id = %s") < sql.index("LIMIT")
    assert "wd.document_id = c.document_id" in sql
    assert 42 in params and 7 in params


def test_fusion_forwards_scope_to_both_retrievers(monkeypatch):
    from app.retrieval import fusion
    vector_search, keyword_search = Mock(return_value=[]), Mock(return_value=[])
    monkeypatch.setattr(fusion, "search_vector", vector_search)
    monkeypatch.setattr(fusion, "search_keyword", keyword_search)
    fusion.search_hybrid("test", top_k=2, workspace_id=17)
    assert vector_search.call_args.kwargs["workspace_id"] == 17
    assert keyword_search.call_args.kwargs["workspace_id"] == 17


@pytest.mark.skipif(os.getenv("EVIDENCERAG_INTEGRATION") != "1", reason="Requires PostgreSQL")
def test_partial_keyword_search_preserves_scope_and_explicit_syntax(monkeypatch):
    with get_connection() as conn, conn.transaction(force_rollback=True):
        monkeypatch.setattr(keyword, "get_connection", lambda: nullcontext(conn))
        workspace = conn.execute("INSERT INTO workspaces(name) VALUES ('Keyword fixture') RETURNING id").fetchone()[0]
        for included in (True, False):
            doc = conn.execute(
                "INSERT INTO documents(title,filename,file_hash) VALUES ('Fixture','fixture.pdf',%s) RETURNING id",
                (uuid4().hex * 2,),
            ).fetchone()[0]
            conn.execute("""
                INSERT INTO chunks(document_id,chunk_index,text,page_start,page_end,embedding_model,embedding_dimensions)
                VALUES (%s,0,'The calibrated spectrometer measured photon counts.',1,1,'fixture',3)
            """, (doc,))
            if included:
                scoped_doc = doc
                conn.execute("INSERT INTO workspace_documents(workspace_id,document_id) VALUES (%s,%s)", (workspace, doc))
        scope = {"workspace_id": workspace, "top_k": 4}
        assert keyword.search_keyword("spectrometer instrument details", **scope) == []
        results = keyword.search_keyword("spectrometer instrument details", allow_partial=True, **scope)
        assert [row["document_id"] for row in results] == [scoped_doc]
        for explicit in ('"spectrometer details"', "spectrometer -photon", "spectrometer details OR nonexistent"):
            assert keyword.search_keyword(explicit, allow_partial=True, **scope) == []
