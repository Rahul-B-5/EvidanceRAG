from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.retrieval import keyword, vector


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
