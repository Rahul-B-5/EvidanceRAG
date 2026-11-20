import os
from contextlib import nullcontext
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.db.connection import get_connection
from research.reproducibility import assess_document


def test_specific_disclosure_outranks_mentions_and_ignores_other_document(monkeypatch):
    calls = []

    def search(query, top_k, document_id, workspace_id):
        calls.append((top_k, document_id, workspace_id))
        base = {"document_id": 3, "page_start": 2, "page_end": 2}
        return [
            {**base, "chunk_id": 1, "text": "Several random seeds were considered."},
            {**base, "document_id": 8, "chunk_id": 2, "text": "The random seed was 17. GPU used: A100."},
            {**base, "chunk_id": 3, "text": "The random seed was 42. GPU details were unavailable."},
        ]
    monkeypatch.setattr("research.reproducibility.search_keyword", search)
    items = {item["label"]: item for item in assess_document(3, 11)}
    seed = items["Random seeds"]
    assert seed["status"] == "specific_detail" and seed["matched_text"] == "random seed was 42"
    assert seed["source"] == {"document_id": 3, "chunk_id": 3, "page_start": 2, "page_end": 2}
    assert items["Hardware and compute"]["status"] == "mention"
    assert items["Code and artifacts"]["status"] == "not_located"
    assert items["Code and artifacts"]["source"] is None
    assert set(calls) == {(5, 3, 11)}


def test_disclosures_keep_missing_values_and_conflicting_availability_separate(monkeypatch):
    source = {"document_id":3, "page_start":2, "page_end":2}
    monkeypatch.setattr("research.reproducibility.search_keyword", lambda *args, **kwargs: [
        {**source, "chunk_id":1, "text":"The learning rate was 3e-4. The code is available only upon request."},
        {**source, "chunk_id":2, "text":"The code is publicly available at https://github.com/org/research. The commit SHA was not specified."},
        {**source, "document_id":4, "chunk_id":3, "text":"The batch size was 32."},
    ])
    assessment = assess_document(3, None)
    checks = {check["label"]: check for item in assessment for check in item["disclosures"]}
    assert checks["Learning rate"]["evidence"][0]["match"] == "learning rate was 3e-4"
    assert checks["Batch size"]["status"] == checks["Version pin"]["status"] == "not_located"
    assert checks["Repository locator"]["evidence"][0]["match"] == "https://github.com/org/research"
    availability = checks["Code availability"]
    assert availability["status"] == "mixed"
    assert {hit["kind"]: hit["source"]["chunk_id"] for hit in availability["evidence"]} == {
        "reported": 2, "limitation": 1,
    }
    assert availability["evidence"][0]["excerpt"] == "The code is available only upon request."


@pytest.mark.skipif(os.getenv("EVIDENCERAG_INTEGRATION") != "1", reason="Requires PostgreSQL")
def test_dossier_checks_workspace_and_returns_source_indexed_detail(monkeypatch):
    with get_connection() as conn, conn.transaction(force_rollback=True):
        monkeypatch.setattr("app.api.main.get_connection", lambda: nullcontext(conn))
        monkeypatch.setattr("app.retrieval.keyword.get_connection", lambda: nullcontext(conn))
        workspace = conn.execute("INSERT INTO workspaces(name) VALUES ('Dossier fixture') RETURNING id").fetchone()[0]
        doc = conn.execute("""
            INSERT INTO documents(title,filename,file_hash) VALUES ('Dossier source','fixture.pdf',%s)
            RETURNING id
        """, (uuid4().hex * 2,)).fetchone()[0]
        chunk = conn.execute("""
            INSERT INTO chunks(document_id,chunk_index,text,page_start,page_end,embedding_model,embedding_dimensions)
            VALUES (%s,0,'The random seed was 42. We used a single A100 GPU.',4,4,'fixture',3) RETURNING id
        """, (doc,)).fetchone()[0]
        endpoint = f"/documents/{doc}/reproducibility"
        client = TestClient(app)
        assert client.get(endpoint, params={"workspace_id": workspace}).status_code == 422
        conn.execute("INSERT INTO workspace_documents(workspace_id,document_id) VALUES (%s,%s)", (workspace, doc))
        response = client.get(endpoint, params={"workspace_id": workspace})
        assert response.status_code == 200
        items = {item["label"]: item for item in response.json()["items"]}
        assert items["Random seeds"]["source"]["chunk_id"] == chunk
        assert items["Random seeds"]["disclosures"][0]["evidence"][0]["source"]["chunk_id"] == chunk
        assert items["Hardware and compute"]["matched_text"] == "A100"
        assert items["Code and artifacts"]["status"] == "not_located"
