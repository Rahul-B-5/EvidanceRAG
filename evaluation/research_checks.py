"""Gold checks for comparison, research directions and reproducibility on paper excerpts."""
import json
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import patch

from research import gaps, structured


def comparison_finding(conn, document_id: int, index: int, outcome: dict) -> tuple[list[dict], int]:
    row = conn.execute("""
        SELECT id, document_id, page_start, page_end, text FROM chunks
        WHERE document_id = %s AND chunk_index = %s
    """, (document_id, index)).fetchone()
    passage = dict(zip(("chunk_id", "document_id", "page_start", "page_end", "text"), row, strict=True))
    candidate = {"topic": "results", "source": 1, **outcome}
    provider = SimpleNamespace(generate_json=lambda **_: json.dumps({"findings": [candidate]}))
    return structured.extract_findings(provider, [passage])


def research_checks(client, conn, docs: dict, workspaces: dict) -> dict[str, bool]:
    workspace = workspaces["reading-comprehension"]
    human_v1, _ = comparison_finding(conn, docs["squad"], 1, {
        "metric": "F1 score", "value": "86.8%", "dataset": "SQuAD v1.0", "split": "test split", "baseline": "human",
    })
    docqa, _ = comparison_finding(conn, docs["squad2"], 1, {
        "metric": "F1", "value": "66.3%", "dataset": "SQuAD 2.0", "split": "test split", "subject": "DocQA + ELMo",
    })
    bert, _ = comparison_finding(conn, docs["bert"], 0, {
        "metric": "F1 score", "value": "83.1%", "dataset": "SQuAD 2.0", "subject": "BERT Large",
    })
    swapped, rejected = comparison_finding(conn, docs["bert"], 0, {"metric": "F1 score", "value": "80.0%"})
    pairs = structured.comparison_result([
        {"document_id": docs["squad"], "title": "SQuAD v1.0", "findings": human_v1},
        {"document_id": docs["squad2"], "title": "SQuAD 2.0", "findings": docqa},
        {"document_id": docs["bert"], "title": "BERT", "findings": bert},
    ], conn)
    checks = {
        "cross_version_comparison_flags_the_dataset": any(
            item["status"] == "reported_difference" and "dataset" in item["differences"]
            for item in pairs["checks"][0]["outcomes"]
        ),
        "same_dataset_and_metric_with_missing_conditions_stays_uncertain": any(
            item["status"] == "insufficient_context" for item in pairs["checks"][2]["outcomes"]
        ),
        "different_scores_do_not_create_a_contradiction": bool(human_v1 and docqa and bert) and not pairs["contradictions"],
        "numeric_comparison_rejects_a_value_bound_to_another_metric": not swapped and rejected == 1,
    }

    with patch.object(gaps, "get_connection", lambda: nullcontext(conn)):
        directions = client.get("/research/directions", params={"workspace_id": workspace}).json()
    evaluation = next((item for item in directions.get("directions", []) if item["id"] == "evaluation"), {})
    checks["gap_reports_scope_limited_to_spans_with_page_provenance"] = (
        evaluation.get("verification") == "requires_broader_verification" and
        any(item["document_id"] == docs["squad"] and item["page_start"] == item["page_end"] == 2 and
            "limited to answers" in item["excerpt"] for item in evaluation["evidence"])
    )
    checks["discussion_of_no_answer_does_not_invent_a_gap"] = not any(
        item["document_id"] == docs["squad2"] and "must abstain" in item["excerpt"]
        for direction in directions.get("directions", []) for item in direction["evidence"]
    )
    record = client.get(f"/documents/{docs['bert']}/reproducibility", params={"workspace_id": workspace}).json()
    components = {item["label"]: item for item in record.get("items", [])}
    training = components.get("Training settings", {})
    seed = components.get("Random seeds", {})
    checks["reproduction_extracts_fine_tuning_with_the_correct_page"] = (
        training.get("status") == "specific_detail" and
        "batch size of 48" in training["excerpt"] and
        training["source"]["document_id"] == docs["bert"] and training["source"]["page_start"] == 7
    )
    checks["reproduction_recognizes_seed_mention_without_inventing_values"] = seed.get("status") == "mention"
    return checks
