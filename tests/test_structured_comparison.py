import json
import os
from contextlib import nullcontext
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.db.connection import get_connection
from research.structured import extract_findings, pairwise_checks, reproducibility_mentions


def test_quotes_and_numerical_fields_are_grounded_in_the_same_passage():
    quote = "F1 was 87% on the held-out split of Set A."
    passage = {"text": quote.replace("held-out split", "held-out\n split"),
               "document_id": 8, "chunk_id": 3, "page_start": 2, "page_end": 3}
    result = {"topic": "results", "source": 1, "metric": "F1", "value": "87%"}
    provider = Mock()
    provider.generate_json.return_value = json.dumps({"findings": [
        {**result, "quote": "Fabricated quote ignored by the server.", "dataset": "Invented dataset", "split": "held-out"},
        {**result, "source": 2},
        {**result, "value": "99%"},
        {**result, "value": "87"},
        {**result, "value": "7%"},
    ]})
    findings, rejected = extract_findings(provider, [passage])
    assert rejected == 4
    assert findings == [{
        "topic": "results", "quote": quote,
        "source": {"document_id": 8, "chunk_id": 3, "page_start": 2, "page_end": 3, "excerpt_id": "3:0:10"},
        "outcome": {"metric": "F1", "split": "held-out", "value": "87%"},
    }]


@pytest.mark.parametrize(("right", "status", "difference"), [
    ({"dataset": "Set B"}, "reported_difference", "dataset"),
    ({"value": "0.87"}, "reported_difference", "reported scale"),
    ({"split": None}, "insufficient_context", None),
    ({}, "candidate_match", None),
])
def test_comparability_flags_differences_and_missing_conditions(right, status, difference):
    shared = {"metric": "F1", "value": "87%", "dataset": "Set A", "task": "classification",
              "split": "held-out", "protocol": "five seeds", "baseline": "linear model"}
    papers = [
        {"document_id": 1, "findings": [{"outcome": shared}]},
        {"document_id": 2, "findings": [{"outcome": {**shared, **right}}]},
    ]
    check = pairwise_checks(papers)[0]["outcomes"][0]
    assert check["status"] == status
    if difference:
        assert difference in check["differences"]
    if "split" in right and right["split"] is None:
        assert check["missing"] == ["split"]


def test_malformed_provider_result_surfaces_error():
    provider = Mock()
    provider.generate_json.return_value = '{"findings":{}}'
    with pytest.raises(RuntimeError, match="invalid comparison response"):
        extract_findings(provider, [])


def test_model_selects_indexed_window_without_retyping_it():
    prefix = "This experimental paper describes baseline details. " * 13
    text = prefix + "The final benchmark F1 score was 87%."
    passage = {"text": text, "document_id": 8, "chunk_id": 3, "page_start": 2, "page_end": 3}
    provider = Mock()

    def generate(*, prompt, system_instruction):
        label = next(key for key, excerpt in json.loads(prompt).items() if "87%" in excerpt)
        return json.dumps({"findings": [{"topic": "results", "source": label, "metric": "F1", "value": "87%"}]})

    provider.generate_json.side_effect = generate
    findings, rejected = extract_findings(provider, [passage])
    assert rejected == 0
    assert findings[0]["quote"] in text
    assert findings[0]["outcome"]["value"] == "87%"


@pytest.mark.parametrize(("literal", "expected"), [("20", False), ("20 ms", True)])
def test_latency_requires_source_unit(literal, expected):
    provider = Mock()
    quote = "The system recorded latency of 20 ms on the reference device."
    provider.generate_json.return_value = json.dumps({"findings": [
        {"topic": "results", "source": 1, "metric": "latency", "value": literal, "baseline": "nonexistent"}
    ]})
    passage = {"text": quote, "document_id": 8, "chunk_id": 3, "page_start": 2, "page_end": 3}
    findings, rejected = extract_findings(provider, [passage])
    assert bool(findings) is expected
    assert rejected == (0 if expected else 1)
    if expected:
        assert "baseline" not in findings[0]["outcome"]


@pytest.mark.parametrize(("value", "quote"), [("20%", "Performance changed by -20%."), ("1", "The trial had 1,000 cases.")])
def test_numeric_fields_cannot_extract_fragment_of_signed_or_grouped_number(value, quote):
    from research.structured import reported_value_in

    assert not reported_value_in(value, quote)


def test_reproducibility_reports_mention_without_inventing_unseen_details(monkeypatch):
    search = Mock(return_value=[{"text": "We ran the benchmark across five groups and 3 random seeds.",
                                 "document_id": 6, "chunk_id": 20, "page_start": 4, "page_end": 4}])
    monkeypatch.setattr("research.structured.search_keyword", search)
    checks = {item["item"]: item["mention"] for item in reproducibility_mentions(6, 17)}
    assert checks["Random seeds"]["source"]["chunk_id"] == 20
    assert checks["Compute"] is None
    assert all(call.kwargs["workspace_id"] == 17 for call in search.call_args_list)


@pytest.mark.skipif(os.environ.get("EVIDENCERAG_INTEGRATION") != "1", reason="Requires local PostgreSQL")
def test_structured_api_verifies_sources_and_comparability_in_workspace(monkeypatch):
    with get_connection() as conn, conn.transaction(force_rollback=True):
        workspace = conn.execute("INSERT INTO workspaces(name) VALUES ('Comparison fixture') RETURNING id").fetchone()[0]
        ids, chunks = [], []
        model = Mock()

        def extract(*, prompt, system_instruction):
            source, quote = next(iter(json.loads(prompt).items()))
            dataset = "Set A" if "Set A" in quote else "Set B"
            return json.dumps({"findings": [{"topic": "results", "source": source, "quote": quote,
                            "metric": "F1", "value": "87%", "dataset": dataset}]})

        model.generate_json.side_effect = extract
        for dataset in ("Set A", "Set B"):
            doc = conn.execute(
                "INSERT INTO documents(title, filename, file_hash) VALUES (%s,'fixture.pdf',%s) RETURNING id",
                (dataset, uuid4().hex * 2),
            ).fetchone()[0]
            ids.append(doc)
            chunks.append(conn.execute("""
                INSERT INTO chunks(document_id, chunk_index, text, page_start, page_end, embedding_model, embedding_dimensions)
                VALUES (%s,0,%s,2,2,'fixture',3) RETURNING id
            """, (doc, f"Benchmark F1 was 87% on dataset {dataset}.")).fetchone()[0])
        conn.execute("INSERT INTO workspace_documents(workspace_id, document_id) VALUES (%s,%s)", (workspace, ids[0]))
        monkeypatch.setattr("app.api.main.get_connection", lambda: nullcontext(conn))
        monkeypatch.setattr("app.retrieval.keyword.get_connection", lambda: nullcontext(conn))
        monkeypatch.setattr("research.structured.get_generation_provider", lambda _: model)
        client = TestClient(app)
        payload = {"document_ids": ids, "workspace_id": workspace}
        assert client.post("/comparisons/structured", json=payload).status_code == 422
        model.generate_json.assert_not_called()
        conn.execute("INSERT INTO workspace_documents(workspace_id, document_id) VALUES (%s,%s)", (workspace, ids[1]))
        response = client.post("/comparisons/structured", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert [p["findings"][0]["source"]["chunk_id"] for p in data["papers"]] == chunks
        assert data["checks"][0]["outcomes"][0]["differences"] == ["dataset"]
