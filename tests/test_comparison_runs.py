import os
from contextlib import nullcontext
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.db.connection import get_connection
from research import comparison_runs as jobs

pytestmark = pytest.mark.skipif(os.getenv("EVIDENCERAG_INTEGRATION") != "1", reason="Requires PostgreSQL")


@pytest.fixture
def fixture(monkeypatch):
    with get_connection() as conn, conn.transaction(force_rollback=True):
        monkeypatch.setattr(jobs, "get_connection", lambda: nullcontext(conn))
        monkeypatch.setattr("app.api.main.get_connection", lambda: nullcontext(conn))
        workspace = conn.execute("INSERT INTO workspaces(name) VALUES ('Run fixture') RETURNING id").fetchone()[0]
        titles = {}
        for title in ("First paper", "Second paper"):
            id_ = conn.execute("""
                INSERT INTO documents(title, filename, file_hash) VALUES (%s,'fixture.pdf',%s) RETURNING id
            """, (title, uuid4().hex * 2)).fetchone()[0]
            titles[id_] = title
            conn.execute("INSERT INTO workspace_documents VALUES (%s,%s)", (workspace, id_))
        yield conn, workspace, titles


def test_comparison_keeps_each_result_and_invalidates_removed_workspace_scope(fixture, monkeypatch):
    conn, workspace, titles = fixture
    client = TestClient(app)

    def extract(id_, title, scope):
        assert scope == workspace
        history = jobs.list_runs(workspace)
        assert len(history) == 1
        run = jobs.run_details(history[0]["id"])
        assert run["status"] == "running"
        assert len(run["result"]["papers"]) == list(titles).index(id_)
        return {"document_id": id_, "title": title, "findings": []}

    monkeypatch.setattr(jobs, "extract_paper", extract)
    response = client.post("/comparison-runs", json={"document_ids": list(titles), "workspace_id": workspace})
    assert response.status_code == 202
    id_ = response.json()["id"]
    run = client.get(f"/comparison-runs/{id_}").json()
    assert run["status"] == "completed"
    assert [paper["title"] for paper in run["result"]["papers"]] == list(titles.values())
    assert client.get("/comparison-runs").json()["runs"] == []
    conn.execute("DELETE FROM workspace_documents WHERE workspace_id=%s AND document_id=%s", (workspace, next(iter(titles))))
    assert client.get(f"/comparison-runs/{id_}").status_code == 422
    assert client.get("/comparison-runs", params={"workspace_id": workspace}).json()["runs"] == []


def test_expired_worker_releases_slot_and_cancel_stops_next_paper(fixture, monkeypatch):
    conn, workspace, titles = fixture
    first = jobs.create_run(titles, workspace)["id"]
    assert jobs.create_run(titles, workspace) is None
    conn.execute("UPDATE comparison_runs SET lease_until=NOW()-INTERVAL '1 second' WHERE id=%s", (first,))
    second = jobs.create_run(titles, workspace)["id"]
    assert jobs.run_details(first)["status"] == "interrupted"
    seen = []

    def cancel_in_flight(id_, title, scope):
        seen.append(id_)
        assert jobs.cancel_run(second)
        return {"document_id": id_, "title": title, "findings": []}

    monkeypatch.setattr(jobs, "extract_paper", cancel_in_flight)
    jobs.execute_run(second, titles, workspace)
    assert seen == [next(iter(titles))]
    run = jobs.run_details(second)
    assert run["status"] == "cancelled"
    assert run["result"]["papers"] == []


def test_failed_paper_preserves_preceding_results(fixture, monkeypatch):
    _, workspace, titles = fixture
    run = jobs.create_run(titles, workspace)

    def extract(id_, title, scope):
        if id_ == list(titles)[1]:
            raise RuntimeError("Generation provider timed out.")
        return {"document_id": id_, "title": title, "findings": []}

    monkeypatch.setattr(jobs, "extract_paper", extract)
    jobs.execute_run(run["id"], titles, workspace)
    current = jobs.run_details(run["id"])
    assert current["status"] == "failed"
    assert current["error"] == "Generation provider timed out."
    assert len(current["result"]["papers"]) == 1
