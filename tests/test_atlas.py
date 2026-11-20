import os
from contextlib import nullcontext
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from app.api.main import app
from app.db.connection import get_connection
from research.atlas import build_atlas


def finding(doc: int, chunk: int, label: str = "F1") -> dict:
    return {"topic": "results", "quote": f"{label} was 87% in the Orchard benchmark.",
            "source": {"document_id": doc, "chunk_id": chunk, "page_start": 2, "page_end": 2},
            "outcome": {"metric": label, "dataset": "Orchard", "value": "87%"}}


def test_edges_keep_citations_and_deduplicate_shared_metric_labels():
    papers = [
        {"document_id": 1, "title": "Paper one", "findings": [finding(1, 12), finding(4, 99)]},
        {"document_id": 2, "title": "Paper two", "findings": [finding(2, 13, "f1")]},
    ]
    result = build_atlas(papers)
    assert result == build_atlas(papers)
    assert sum(n["kind"] == "metric" for n in result["nodes"]) == 1
    assert sum(n["kind"] == "dataset" for n in result["nodes"]) == 1
    assert {e["provenance"]["chunk_id"] for e in result["edges"]} == {12, 13}
    ids = {n["id"] for n in result["nodes"]}
    assert all(e["source"] in ids and e["target"] in ids for e in result["edges"])


@pytest.mark.skipif(os.getenv("EVIDENCERAG_INTEGRATION") != "1", reason="Requires PostgreSQL")
def test_atlas_rebuilds_current_workspace_graph_from_persisted_results(monkeypatch):
    with get_connection() as conn, conn.transaction(force_rollback=True):
        monkeypatch.setattr("app.api.main.get_connection", lambda: nullcontext(conn))
        monkeypatch.setattr("research.atlas.get_connection", lambda: nullcontext(conn))
        workspace = conn.execute("INSERT INTO workspaces(name) VALUES ('Atlas fixture') RETURNING id").fetchone()[0]
        papers = []
        for title in ("Atlas fixture A", "Atlas fixture B"):
            doc = conn.execute("""
                INSERT INTO documents(title, filename, file_hash) VALUES (%s,'fixture.pdf',%s) RETURNING id
            """, (title, uuid4().hex * 2)).fetchone()[0]
            conn.execute("INSERT INTO workspace_documents(workspace_id, document_id) VALUES (%s,%s)", (workspace, doc))
            chunk = conn.execute("""
                INSERT INTO chunks(document_id,chunk_index,text,page_start,page_end,embedding_model,embedding_dimensions)
                VALUES (%s,0,'F1 was 87%% in the Orchard benchmark.',2,2,'fixture',3) RETURNING id
            """, (doc,)).fetchone()[0]
            papers.append({"document_id": doc, "title": title, "findings": [finding(doc, chunk)]})
        ids = [p["document_id"] for p in papers]
        conn.execute("""
            INSERT INTO comparison_runs(id, workspace_id, document_ids, titles, papers, status, lease_until)
            VALUES (%s,%s,%s,%s,%s,'completed',NOW())
        """, (uuid4(), workspace, ids, [p["title"] for p in papers], Jsonb(papers)))
        client = TestClient(app)
        assert client.get("/evidence-atlas", params={"workspace_id": workspace}).json() == build_atlas(sorted(papers, key=lambda p: -p["document_id"]))
        conn.execute("DELETE FROM workspace_documents WHERE workspace_id=%s AND document_id=%s", (workspace, ids[0]))
        graph = client.get("/evidence-atlas", params={"workspace_id": workspace}).json()
        assert graph == build_atlas(papers[1:])
        global_graph = client.get("/evidence-atlas").json()
        assert all(e["provenance"]["document_id"] not in ids for e in global_graph["edges"])
