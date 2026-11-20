import os
from contextlib import nullcontext
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.db.connection import get_connection
from research import comparison_runs


@pytest.mark.skipif(os.getenv("EVIDENCERAG_INTEGRATION") != "1", reason="Requires PostgreSQL")
def test_comparison_publishes_exact_scoped_claims_and_researcher_assessments(monkeypatch):
    with get_connection() as conn, conn.transaction(force_rollback=True):
        for module in ("app.api.main", "app.api.claims", "app.api.related_papers", "research.comparison_runs", "research.atlas"):
            monkeypatch.setattr(f"{module}.get_connection", lambda: nullcontext(conn))
        workspace = conn.execute("INSERT INTO workspaces(name) VALUES ('Claim fixture') RETURNING id").fetchone()[0]
        paper_findings = {}
        for index, value in enumerate((87, 82)):
            title = f"Claim fixture {index}"
            paper = conn.execute("""
                INSERT INTO documents(title,filename,file_hash) VALUES (%s,'fixture.pdf',%s) RETURNING id
            """, (title, uuid4().hex * 2)).fetchone()[0]
            conn.execute("INSERT INTO workspace_documents(workspace_id,document_id) VALUES (%s,%s)", (workspace,paper))
            raw = f"The OrchardBench \nF1 score was {value} percent."
            chunk = conn.execute("""
                INSERT INTO chunks(document_id,chunk_index,text,page_start,page_end,embedding_model,embedding_dimensions)
                VALUES (%s,0,%s,3,4,'fixture',3) RETURNING id
            """, (paper, raw)).fetchone()[0]
            finding = {"topic":"results","quote":" ".join(raw.split()),
                       "source":{"document_id":paper,"chunk_id":chunk,"page_start":3,"page_end":4},
                       "outcome":{"metric":"F1","dataset":"OrchardBench","value":str(value)}}
            paper_findings[paper] = {"document_id":paper,"title":title,
                                     "findings":[finding,{**finding, "quote":"Unsupported invented excerpt."}]}
        monkeypatch.setattr(comparison_runs, "extract_paper", lambda id_, *_: paper_findings[id_])
        client = TestClient(app)
        scope = {"workspace_id":workspace}
        response = client.post("/comparison-runs", json={**scope,"document_ids":list(paper_findings)})
        assert response.status_code == 202
        run = client.get(f"/comparison-runs/{response.json()['id']}").json()
        first, second = list(paper_findings)
        claim = run["result"]["papers"][0]["findings"][0]["claim_id"]
        rows = client.get("/claims", params={**scope,"query":"orchardbench","limit":1}).json()
        assert rows["has_more"] and len(rows["claims"]) == 1
        assert client.get("/claims", params={**scope,"query":"invented"}).json()["claims"] == []
        path = f"/claims/{claim}"
        detail = client.get(path, params=scope).json()
        assert detail["finding"]["source"]["page_end"] == 4
        assert detail["assessment"] is None
        assert detail["related"][0]["document_id"] == second
        assert detail["related"][0]["shared_labels"] == {"metric":"F1","dataset":"OrchardBench"}
        related_url = f"/documents/{first}/related-papers"
        recommendations = client.get(related_url, params=scope).json()["papers"]
        assert len(recommendations) == 1
        recommendation = recommendations[0]
        assert recommendation["document_id"] == second and recommendation["origin_claim_id"] == claim
        assert recommendation["source"]["page_end"] == recommendation["origin_source"]["page_end"] == 4
        assert client.get(related_url).json()["papers"] == []
        assert client.get(path).status_code == 404
        assessment = {"status":"qualified","note":"Confirm the test split.","revision":0}
        assert client.put(path + "/assessment", params=scope, json=assessment).status_code == 200
        assert client.put(path + "/assessment", params=scope, json=assessment).status_code == 409
        assert client.get("/claims", params={**scope,"status":"qualified"}).json()["claims"][0]["id"] == claim
        assert any(n["id"] == claim for n in client.get("/evidence-atlas", params={**scope,"focus":claim}).json()["nodes"])
        conn.execute("DELETE FROM workspace_documents WHERE workspace_id=%s AND document_id=%s", (workspace,second))
        assert client.get(path, params=scope).json()["related"] == []
        assert client.get(related_url, params=scope).json()["papers"] == []
        conn.execute("DELETE FROM workspace_documents WHERE workspace_id=%s AND document_id=%s", (workspace,first))
        assert client.get(path, params=scope).status_code == 404
        assert client.get("/claims", params=scope).json()["claims"] == []
