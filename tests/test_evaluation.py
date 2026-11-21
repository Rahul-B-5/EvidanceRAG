import os
from types import SimpleNamespace

import pytest

from app.db.connection import get_connection
from evaluation.database import fresh_schema
from evaluation.pdf_benchmark import check_answer as check_pdf_answer
from evaluation.run import answer_checks, contains_answer_value, evaluate, retrieval_metrics


def test_retrieval_metrics_check_rank_and_empty_reference_set():
    assert retrieval_metrics(["distractor", "relevant"], {"relevant", "missing"}) == {
        "precision": 0.25, "recall": 0.5, "reciprocal_rank": 0.5,
    }
    assert all(value is None for value in retrieval_metrics([], set()).values())


def test_value_matching_rejects_substrings_and_preserves_percentage_scale():
    assert contains_answer_value("Balanced accuracy was 71 percent.", "71%")
    assert contains_answer_value("37 observations were included.", "37")
    assert not contains_answer_value("There were 137 observations.", "37")
    assert not contains_answer_value("The sample was 37.5 observations.", "37")
    assert not contains_answer_value("Balanced accuracy was 71 units.", "71%")
    assert contains_answer_value("There were 107,785 examples.", "107785")
    assert contains_answer_value("Exact match was 77%.", "77.0%")
    assert contains_answer_value("BERT Base has 110 million parameters.", "110M")
    assert contains_answer_value("The size is 110M.", "110M")
    assert not contains_answer_value("The size is 1110M.", "110M")
    assert not contains_answer_value("The capacity is 110 MW.", "110M")


@pytest.mark.skipif(os.getenv("EVIDENCERAG_INTEGRATION") != "1", reason="Requires PostgreSQL")
def test_synthetic_evaluation_checks_real_retrieval_and_leaves_no_fixture_schema(monkeypatch):
    schema = fresh_schema()
    monkeypatch.setattr("evaluation.run.fresh_schema", lambda: schema)

    def schema_exists():
        with get_connection() as conn:
            return conn.execute("SELECT 1 FROM pg_namespace WHERE nspname=%s", (schema,)).fetchone() is not None

    assert not schema_exists()
    report = evaluate()
    assert report["passed"] == report["case_count"], [case for case in report["cases"] if not case["passed"]]
    assert report["retrieval"]["hybrid"]["recall"] == 1
    assert not schema_exists()


def test_statement_support_flags_swapped_but_existing_citations():
    citations = [
        {"evidence_id": "E1", "chunk_id": 1, "document_id": 1, "page_start": 3, "page_end": 3},
        {"evidence_id": "E2", "chunk_id": 2, "document_id": 2, "page_start": 7, "page_end": 7},
    ]
    case = {"expected": ["docqa", "bert"], "fixture_answer": "sample",
            "answer_contains": ["66.3%", "83.1%"], "support": {"66.3%": "docqa", "83.1%": "bert"}}
    response = SimpleNamespace(status_code=200, json=lambda: {
        "answer": "DocQA reports 66.3% [E2]. BERT reports 83.1% [E1].",
        "abstained": False, "citations": citations, "evidence": citations,
    })
    checks = answer_checks(response, case, {1: "docqa", 2: "bert"}, {1: (1, 3, 3), 2: (2, 7, 7)}, {1, 2})
    assert checks["citations"] and checks["required_values"]
    assert not checks["statement_citation_support"]


@pytest.mark.skipif(os.getenv("EVIDENCERAG_INTEGRATION") != "1", reason="Requires PostgreSQL")
def test_public_paper_evaluation_exercises_research_workflows():
    report = evaluate(corpus="reading-comprehension")
    assert report["passed"] == report["case_count"] == 5, [case for case in report["cases"] if not case["passed"]]
    assert len(report["research_checks"]) == 8
    assert all(report["research_checks"].values()), report["research_checks"]


def test_whole_report_rubric_requires_the_two_correct_physical_pages():
    summary = {"evidence_id": "E1", "document_id": 1, "chunk_id": 7, "page_start": 7, "page_end": 7}
    table = {"evidence_id": "E2", "document_id": 1, "chunk_id": 45, "page_start": 45, "page_end": 45}
    payload = {"abstained": False, "citations": [summary, table],
               "evidence": [{**summary, "text": "The modeled price was 1.16."},
                            {**table, "text": "Table 3 lists 1.17."}]}
    facts = {"1.16": (7,), "1.17": (45,)}
    assert all(check_pdf_answer({**payload, "answer": "Summary: 1.16 [E1]. Table 3: 1.17 [E2]."}, facts, (), 1).values())
    swapped = check_pdf_answer({**payload, "answer": "Summary: 1.16 [E2]. Table 3: 1.17 [E1]."}, facts, (), 1)
    assert swapped["source_anchors"] and not swapped["cited_facts"]
def test_bert_whole_pdf_gold_preserves_training_setting_associations():
    import json
    import re
    from pathlib import Path

    spec = json.loads((Path(__file__).parents[1] / "evaluation" / "bert_pdf.json").read_text())
    patterns = spec["answer_relations"]["squad2-training-settings"]
    correct = "The model used 2 epochs with a batch size of 48."
    swapped = "The model used 48 epochs with a batch size of 2."
    assert all(re.search(pattern, correct, re.I) for pattern in patterns)
    assert not all(re.search(pattern, swapped, re.I) for pattern in patterns)
