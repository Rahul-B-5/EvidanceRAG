from contextlib import nullcontext
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from app.api.main import app

client = TestClient(app)


@pytest.mark.parametrize("ids", [[1, 1], [0, 2], [-1, 2], [1]])
def test_invalid_comparison_ids_do_not_access_database(monkeypatch, ids):
    connection = Mock(side_effect=AssertionError("Invalid input reached database"))
    monkeypatch.setattr("app.api.main.get_connection", connection)
    assert client.post("/comparisons", json={"document_ids": ids}).status_code == 422
    connection.assert_not_called()


def test_missing_document_does_not_masquerade_as_missing_evidence(monkeypatch):
    conn = Mock()
    conn.execute.return_value.fetchall.return_value = [(2, "Available paper")]
    monkeypatch.setattr("app.api.main.get_connection", lambda: nullcontext(conn))
    compare = Mock()
    monkeypatch.setattr("app.api.main.compare_documents", compare)
    response = client.post("/comparisons", json={"document_ids": [1, 2]})
    assert response.status_code == 404
    compare.assert_not_called()


def test_existing_paper_keeps_title_when_no_passages_match(monkeypatch):
    conn = Mock()
    conn.execute.return_value.fetchall.return_value = [(2, "First"), (3, "Second")]
    monkeypatch.setattr("app.api.main.get_connection", lambda: nullcontext(conn))
    monkeypatch.setattr("app.api.main.compare_documents", lambda *args, **kwargs: {
        "papers": [{"document_id": 2, "title": None}, {"document_id": 3, "title": None}]
    })
    response = client.post("/comparisons", json={"document_ids": [2, 3]})
    assert response.status_code == 200
    assert [p["title"] for p in response.json()["papers"]] == ["First", "Second"]
