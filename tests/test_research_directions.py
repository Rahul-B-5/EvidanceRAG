import os
from contextlib import nullcontext
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.db.connection import get_connection
from research.gaps import coverage_excerpt, qualifying_excerpt


def test_topic_without_qualifying_language_does_not_create_a_gap():
    assert qualifying_excerpt("This paper describes generalization across datasets.", r"generalization") is None
    assert qualifying_excerpt("Future work considers datasets." + " Other details." * 40 + " Generalization improved.", r"generalization") is None
    assert qualifying_excerpt("Future work should test generalization at additional sites.", r"generalization") == (
        "Future work should test generalization at additional sites.", "Future work",
    )
    assert qualifying_excerpt("A limitation is memory. Generalization improved.", r"generalization") is None


def test_coverage_requires_reported_action_and_skips_proposals_and_negations():
    pattern = r"evaluated on an external site"
    assert coverage_excerpt("We evaluated on an external site.", pattern) == (
        "We evaluated on an external site.", "evaluated on an external site",
    )
    assert coverage_excerpt("The model may be evaluated on an external site.", pattern) is None
    assert coverage_excerpt("The model was not evaluated on an external site.", pattern) is None
    assert coverage_excerpt("Future work could have the model evaluated on an external site.", pattern) is None


@pytest.mark.skipif(os.getenv("EVIDENCERAG_INTEGRATION") != "1", reason="Requires PostgreSQL")
def test_research_directions_count_distinct_papers_in_scope(monkeypatch):
    with get_connection() as conn, conn.transaction(force_rollback=True):
        monkeypatch.setattr("app.api.main.get_connection", lambda: nullcontext(conn))
        monkeypatch.setattr("research.gaps.get_connection", lambda: nullcontext(conn))
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


@pytest.mark.skipif(os.getenv("EVIDENCERAG_INTEGRATION") != "1", reason="Requires PostgreSQL")
def test_topic_focused_direction_separates_reported_coverage_from_limits(monkeypatch):
    with get_connection() as conn, conn.transaction(force_rollback=True):
        monkeypatch.setattr("app.api.main.get_connection", lambda: nullcontext(conn))
        monkeypatch.setattr("research.gaps.get_connection", lambda: nullcontext(conn))
        workspace = conn.execute("INSERT INTO workspaces(name) VALUES ('Focused directions fixture') RETURNING id").fetchone()[0]
        ids = []
        for index, excerpt in enumerate([
            "Future work should test generalization of OrioleNet at additional sites.",
            "OrioleNet was evaluated on an external site. We measured inference latency of OrioleNet.",
            "We discuss OrioleNet. PloverNet was evaluated on an external site.",
            "OrioleNet was evaluated on an external site in a different workspace.",
        ]):
            paper = conn.execute("""
                INSERT INTO documents(title,filename,file_hash) VALUES (%s,'fixture.pdf',%s) RETURNING id
            """, (f"Focused direction fixture {index}", uuid4().hex * 2)).fetchone()[0]
            ids.append(paper)
            if index < 3:
                conn.execute("INSERT INTO workspace_documents(workspace_id,document_id) VALUES (%s,%s)", (workspace, paper))
            conn.execute("""
                INSERT INTO chunks(document_id,chunk_index,text,page_start,page_end,embedding_model,embedding_dimensions)
                VALUES (%s,0,%s,3,3,'fixture',3)
            """, (paper, excerpt))
        response = TestClient(app).get("/research/directions", params={"focus":"OrioleNet", "workspace_id":workspace})
        assert response.status_code == 200
        data = response.json()
        direction, = data["directions"]
        assert direction["id"] == "generalization" and direction["reviewed_paper_count"] == 3
        assert direction["paper_count"] == direction["coverage_paper_count"] == 1
        assert [entry["document_id"] for entry in direction["evidence"]] == ids[:1]
        assert [entry["document_id"] for entry in direction["coverage"]] == ids[1:2]
        assert data["coverage_only"][0]["id"] == "compute"
