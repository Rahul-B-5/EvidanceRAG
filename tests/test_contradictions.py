import json
import os
from contextlib import nullcontext
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from app.api.main import app
from app.db.connection import get_connection
from research.contradictions import opposing_statements, recover_relative_statement, relative_statement
from research.structured import extract_findings


SETUP = {
    "subject": "OrioleNet", "baseline": "CedarNet", "metric": "F1",
    "dataset": "OrchardBench", "task": "binary classification",
    "split": "fixed test split", "protocol": "10-seed protocol",
}
EXPERIMENT = ("For binary classification on OrchardBench using the fixed test split and 10-seed protocol, "
              "OrioleNet {verb} CedarNet on F1.")


def extract(doc, chunk, verb, **overrides):
    quote = EXPERIMENT.format(verb=verb)
    for field, value in overrides.items():
        quote = quote.replace(SETUP[field], value)
    proposal = SimpleNamespace(generate_json=lambda **_: json.dumps({
        "findings": [{"topic":"results", "source":1, **SETUP, **overrides}],
    }))
    findings, _ = extract_findings(proposal, [{
        "document_id": doc, "chunk_id": chunk, "page_start": 2, "page_end": 2, "text": quote,
    }])
    return {"document_id": doc, "title": f"Experiment {doc}", "findings": findings}


@pytest.mark.parametrize("verb", ("did not outperform", "might outperform", "was expected to outperform"))
def test_unconfirmed_or_qualified_relative_statement_is_not_flagged(verb):
    assert relative_statement(EXPERIMENT.format(verb=verb), SETUP) is None


def test_only_opposing_claims_under_shared_conditions_are_paired():
    positive = extract(1, 101, "outperformed")
    negative = extract(2, 102, "underperformed")
    opposing = opposing_statements([positive, negative])
    assert len(opposing) == 1
    assert opposing[0]["conditions"] == SETUP
    assert opposing[0]["left"]["quote"] == EXPERIMENT.format(verb="outperformed")
    assert opposing[0]["right"]["source"]["page_start"] == 2
    assert opposing_statements([positive, extract(2, 103, "performed better than")]) == []
    assert opposing_statements([positive, extract(2, 103, "underperformed", split="validation split")]) == []
    assert opposing_statements([positive, extract(2, 103, "underperformed", subject="PloverNet")]) == []
    assert opposing_statements([positive, extract(1, 103, "underperformed")]) == []
    positive["findings"] += extract(1, 103, "underperformed")["findings"]
    assert opposing_statements([positive, negative]) == []
    assert relative_statement(EXPERIMENT.format(verb="outperformed"), {**SETUP, "protocol":"new protocol"}) is None


def test_literal_fallback_preserves_complete_setup_when_provider_omits_labels():
    quote = EXPERIMENT.format(verb="outperformed") + " OrioleNet F1 was 87%."
    source = {"document_id": 1, "chunk_id": 2, "page_start": 1, "page_end": 1}
    provider = SimpleNamespace(generate_json=lambda **_: json.dumps({
        "findings":[{"source":1, "topic":"results", "metric":"F1", "value":"87%"}],
    }))
    findings, rejected = extract_findings(provider, [{**source, "text":quote}])
    assert rejected == 0
    assert findings[0]["relative_statement"]["conditions"] == SETUP
    assert findings[0]["relative_statement"]["quote"] == EXPERIMENT.format(verb="outperformed")
    assert recover_relative_statement(quote.replace("fixed test split and ", "")) is None


@pytest.mark.skipif(os.getenv("EVIDENCERAG_INTEGRATION") != "1", reason="Requires PostgreSQL")
def test_opposing_claims_have_two_current_workspace_sources_and_can_be_reviewed(monkeypatch):
    with get_connection() as conn, conn.transaction(force_rollback=True):
        for module in ("app.api.main", "research.atlas", "research.counterevidence", "research.claim_reviews"):
            monkeypatch.setattr(f"{module}.get_connection", lambda: nullcontext(conn))
        workspace = conn.execute("INSERT INTO workspaces(name) VALUES ('Opposition fixture') RETURNING id").fetchone()[0]
        papers = []
        for verb in ("outperformed", "underperformed"):
            doc = conn.execute("""
                INSERT INTO documents(title,filename,file_hash) VALUES (%s,'fixture.pdf',%s) RETURNING id
            """, (verb, uuid4().hex * 2)).fetchone()[0]
            conn.execute("INSERT INTO workspace_documents(workspace_id,document_id) VALUES (%s,%s)", (workspace, doc))
            chunk = conn.execute("""
                INSERT INTO chunks (document_id, chunk_index, text, page_start, page_end, embedding_model, embedding_dimensions)
                VALUES (%s,0,%s,2,2,'fixture',3) RETURNING id
            """, (doc, EXPERIMENT.format(verb=verb))).fetchone()[0]
            papers.append(extract(doc, chunk, verb))
        ids = [p["document_id"] for p in papers]
        run_id = uuid4()
        conn.execute("""
            INSERT INTO comparison_runs(id,workspace_id,document_ids,titles,papers,status,lease_until)
            VALUES (%s,%s,%s,%s,%s,'completed',NOW())
        """, (run_id, workspace, ids, [p["title"] for p in papers], Jsonb(papers)))
        for paper in papers:
            conn.execute("SELECT record_comparison_claims(%s,%s,%s,NOW())", (run_id, workspace, Jsonb(paper)))

        client = TestClient(app)
        scope = {"workspace_id":workspace}
        atlas = client.get("/evidence-atlas", params=scope).json()
        pair, = atlas["contradictions"]
        edge = next(e for e in atlas["edges"] if e["relation"] == "potential_disagreement")
        assert edge["provenance"] == pair["left"]["source"]
        assert edge["related_provenance"] == pair["right"]["source"]
        assert client.get("/evidence-atlas").json()["contradictions"] == []
        path = "/evidence-atlas/" + pair["left"]["finding_id"]
        candidate = client.get(path + "/counterevidence", params=scope).json()["passages"][0]
        assert candidate["opposing_statement"]
        assert candidate["excerpt"] == pair["right"]["quote"]
        saved = client.put(path + f"/reviews/{candidate['chunk_id']}", params=scope,
                           json={"relation":"challenges","alignment":"unknown","note":"Review statistical assumptions."})
        assert saved.status_code == 200
        assert saved.json()["candidate_snapshot"] == candidate
        conn.execute("UPDATE chunks SET text='Other indexed text.' WHERE id=%s", (candidate["chunk_id"],))
        assert client.get("/evidence-atlas", params=scope).json()["contradictions"] == []
        conn.execute("DELETE FROM workspace_documents WHERE workspace_id=%s AND document_id=%s",
                     (workspace, candidate["document_id"]))
        assert client.get(path + "/counterevidence", params=scope).json()["reviews"] == []
