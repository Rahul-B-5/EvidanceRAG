import json
import os
from contextlib import nullcontext
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.db.connection import get_connection
from research.coverage import plan_question, question_coverage


def test_question_without_research_subject_is_rejected():
    with pytest.raises(ValueError, match="Add a subject"):
        question_coverage("What was that?", None, False)


def test_provider_gets_question_only_and_duplicate_subquestions_are_rejected(monkeypatch):
    item = {"title": "Methods", "question": "What methods were used?", "keywords": ["method", "training"]}
    provider = Mock()
    provider.generate_json.return_value = json.dumps({"subquestions": [item] * 3})
    monkeypatch.setattr("research.coverage.get_generation_provider", lambda _: provider)
    with pytest.raises(RuntimeError, match="usable subquestion plan"):
        plan_question("How does Orchard classify anomalies?", True)
    args = provider.generate_json.call_args.kwargs
    assert json.loads(args["prompt"]) == {"question": "How does Orchard classify anomalies?"}


@pytest.mark.skipif(os.getenv("EVIDENCERAG_INTEGRATION") != "1", reason="Requires PostgreSQL")
def test_coverage_groups_by_distinct_workspace_papers_and_exposes_missing_facets(monkeypatch):
    with get_connection() as conn, conn.transaction(force_rollback=True):
        monkeypatch.setattr("app.api.main.get_connection", lambda: nullcontext(conn))
        monkeypatch.setattr("research.coverage.get_connection", lambda: nullcontext(conn))
        workspace = conn.execute("INSERT INTO workspaces(name) VALUES ('Coverage fixture') RETURNING id").fetchone()[0]
        fixture_texts = [
            "The Orchard classification method uses a convolutional architecture. The reported accuracy was 94%.",
            "The Orchard classification algorithm uses nearest neighbors.",
            "The Orchard study reports limitations and evaluation results for this benchmark.",
        ]
        ids = []
        for i, text in enumerate(fixture_texts):
            doc = conn.execute("""
                INSERT INTO documents(title,filename,file_hash) VALUES (%s,'fixture.pdf',%s) RETURNING id
            """, (f"Coverage paper {i}", uuid4().hex * 2)).fetchone()[0]
            ids.append(doc)
            for idx in range(2 if i == 0 else 1):
                conn.execute("""
                    INSERT INTO chunks(document_id,chunk_index,text,page_start,page_end,embedding_model,embedding_dimensions)
                    VALUES (%s,%s,%s,2,2,'fixture',3)
                """, (doc, idx, text))
            if i < 2:
                conn.execute("INSERT INTO workspace_documents(workspace_id,document_id) VALUES (%s,%s)", (workspace, doc))
        response = TestClient(app).post("/research/coverage", json={
            "question": "Which approaches address Orchard classification?", "workspace_id": workspace,
        })
        assert response.status_code == 200
        facets = {item["title"]: item for item in response.json()["facets"]}
        assert facets["Approaches"]["status"] == "multiple_papers"
        assert {p["document_id"] for p in facets["Approaches"]["passages"]} == set(ids[:2])
        assert facets["Reported results"]["status"] == "single_paper"
        assert facets["Limitations"]["status"] == "not_located"
