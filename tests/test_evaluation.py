import os

import pytest

from app.db.connection import get_connection
from evaluation.run import contains_answer_value, evaluate, retrieval_metrics


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


@pytest.mark.skipif(os.getenv("EVIDENCERAG_INTEGRATION") != "1", reason="Requires PostgreSQL")
def test_synthetic_evaluation_checks_real_retrieval_and_leaves_no_fixture_schema():
    def schema_count():
        with get_connection() as conn:
            return conn.execute("SELECT count(*) FROM pg_namespace WHERE nspname LIKE 'evidencerag_eval_%'").fetchone()[0]

    before = schema_count()
    report = evaluate()
    assert report["passed"] == report["case_count"], [case for case in report["cases"] if not case["passed"]]
    assert report["retrieval"]["hybrid"]["recall"] == 1
    assert schema_count() == before
