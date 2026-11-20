import os
from contextlib import nullcontext
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.db.connection import get_connection
from research.gaps import qualifying_excerpt


def test_topic_without_qualifying_language_does_not_create_a_gap():
    assert qualifying_excerpt("This paper describes generalization across datasets.", r"generalization") is None
    assert qualifying_excerpt("Future work considers datasets." + " Other details." * 40 + " Generalization improved.", r"generalization") is None
    assert qualifying_excerpt("Future work should test generalization at additional sites.", r"generalization") == (
        "Future work should test generalization at additional sites.", "Future work",
    )


@pytest.mark.skipif(os.getenv("EVIDENCERAG_INTEGRATION") != "1", reason="Requires PostgreSQL")
def test_research_directions_count_distinct_papers_in_scope(monkeypatch):
    with get_connection() as conn, conn.transaction(force_rollback=True):
        monkeypatch.setattr("app.api.main.get_connection", lambda: nullcontext(conn))
        monkeypatch.setattr("app.retrieval.keyword.get_connection", lambda: nullcontext(conn))
        workspace = conn.execute("INSERT INTO workspaces(name) VALUES ('Directions fixture') RETURNING id").fetchone()[0]
        included = set()
        for index, excerpt in enumerate([
            "We only tested on a single dataset. External validation remains an open question.",
            "Future work should test generalization and domain shift in external validation.",
            "The limitation is computational cost and latency.",
        ]):
            document = conn.execute("""
                INSERT INTO documents(title,filename,file_hash) VALUES (%s,'fixture.pdf',%s) RETURNING id
            """, (f"Direction fixture {index}", uuid4().hex * 2)).fetchone()[0]
            if index < 2:
                included.add(document)
                conn.execute("INSERT INTO workspace_documents(workspace_id,document_id) VALUES (%s,%s)", (workspace, document))
            for chunk in range(2):
                conn.execute("""
                    INSERT INTO chunks(document_id,chunk_index,text,page_start,page_end,embedding_model,embedding_dimensions)
                    VALUES (%s,%s,%s,3,4,'fixture',3)
                """, (document, chunk, excerpt))
        response = TestClient(app).get("/research/directions", params={"workspace_id": workspace})
        assert response.status_code == 200
        assert response.json()["reviewed_paper_count"] == 2
        direction = next(d for d in response.json()["directions"] if d["id"] == "generalization")
        assert direction["paper_count"] == 2
        assert direction["verification"] == "requires_broader_verification"
        assert {e["document_id"] for e in direction["evidence"]} == included
        assert not any(d["id"] == "compute" for d in response.json()["directions"])
