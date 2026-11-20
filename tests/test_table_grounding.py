import json
from types import SimpleNamespace

import pytest

from app.generation.answerer import generate_answer
from app.generation.table_grounding import scope_table_answer
from app.ingestion.pdf_extractor import attach_term_definitions


QUESTION = (
    "Compare the Error Rate (ER) for the reference model without augmentation in Overview and Table 2, "
    "with a separate citation for each value."
)


def row(index, label, error, *, page=4, group=""):
    return {
        "evidence_id": f"E{index}", "document_id": 1, "page_start": page, "text": "Indexed row.",
        "table_row": {
            "caption": "Table 2. Calibration results", "group": group,
            "cells": [
                {"column": "Model", "value": label},
                {"column": "ER Score", "value": error},
                {"column": "Precision", "value": "91%"},
            ],
        },
    }


@pytest.fixture
def evidence():
    return [
        {"evidence_id": "E1", "document_id": 1, "page_start": 1,
         "section_title": "Overview", "text": "The reference model has an error rate of 17%."},
        {"evidence_id": "E2", "document_id": 1, "page_start": 4,
         "section_title": "Results", "text": "Raw table text mixes 22%, 29%, and 91%."},
        row(3, "Reference model", "22%"),
        row(4, "Reference model with DA", "29%"),
    ]


def test_grounding_preserves_source_scopes_and_matches_document_defined_terms(evidence):
    attach_term_definitions([
        {"page_number": 1, "text": "We used data augmentation (DA)."},
        {"page_number": 4, "text": "", "table_rows": [item["table_row"] for item in evidence[2:]]},
    ])
    scope = scope_table_answer(QUESTION, evidence)
    assert [source["evidence_id"] for source in scope.sources] == ["E3", "E1"]
    assert [cell["column"] for cell in scope.sources[0]["table_row"]["cells"]] == ["Model", "ER Score"]
    assert scope.supports("Overview: 17% [E1].\nTable 2: 22% [E3].")


@pytest.mark.parametrize("table_statement", [
    "Table 2: 29% [E3].",
    "Table 2: 22 ms [E3].",
    "Table 2: 22% and 91% [E3].",
    "Table 2: 22% [E2].",
    "Table 2: 22% [E3].\nAnother result was 29%.",
])
def test_distractor_metrics_wrong_units_and_raw_table_citations_are_rejected(evidence, table_statement):
    evidence[2]["table_row"]["cells"][0]["value"] = "Reference model without augmentation"
    scope = scope_table_answer(QUESTION, evidence)
    assert not scope.supports(f"Overview: 17% [E1].\n{table_statement}")
    assert not scope.supports("Table 2: 22% [E3].")


def test_unknown_condition_and_multiple_plausible_rows_require_abstention(evidence):
    assert not scope_table_answer(QUESTION, evidence).sources
    evidence[2]["table_row"]["cells"][0]["value"] = "Reference model without augmentation"
    evidence.append(row(5, "Reference model without augmentation", "19%"))
    assert not scope_table_answer(QUESTION, evidence).sources


def test_matching_condition_does_not_substitute_a_different_model_variant(evidence):
    evidence[2]["table_row"]["cells"][0]["value"] = "Reference model variant without augmentation"
    assert not scope_table_answer(QUESTION, evidence).sources
    qualified = QUESTION.replace("reference model ", "reference model variant ")
    assert not scope_table_answer(qualified, evidence).sources
    evidence[0]["text"] = evidence[0]["text"].replace("reference model ", "reference model variant ")
    assert scope_table_answer(qualified, evidence).table_values == {"E3": ["22%"]}


def test_questions_about_both_conditions_do_not_enter_the_exclusion_path(evidence):
    assert scope_table_answer(QUESTION.replace("without", "with and without"), evidence) is None


def test_prose_sources_exclude_other_metrics_and_explicit_alternate_conditions(evidence):
    evidence[2]["table_row"]["cells"][0]["value"] = "Reference model without augmentation"
    evidence[3]["table_row"]["term_definitions"] = {"DA": "data augmentation"}
    evidence[0]["text"] += " The reference model had an error rate of 29% with DA. Its precision was 91%."
    alternative = {**evidence[0], "evidence_id": "E5",
                   "text": "The reference model had an error rate of 31% with augmentation."}
    scope = scope_table_answer(QUESTION, [*evidence, alternative])
    assert [source["evidence_id"] for source in scope.sources] == ["E3", "E1"]
    assert scope.sources[1]["text"] == "The reference model has an error rate of 17%."
    assert not scope.supports("Overview: 29% [E1].\nTable 2: 22% [E3].")


def test_prose_scope_checks_measured_units_while_allowing_cited_context(evidence):
    evidence[2]["table_row"]["cells"][0]["value"] = "Reference model without augmentation"
    evidence[0]["text"] = "The study dates from 2023. The reference model has an error rate of 17%."
    scope = scope_table_answer(QUESTION, evidence)
    assert scope.supports("The 2023 Overview reports 17% [E1].\nTable 2: 22% [E3].")
    assert not scope.supports("The 2024 Overview reports 17% [E1].\nTable 2: 22% [E3].")
    assert not scope.supports("The 2023 Overview reports $17 [E1].\nTable 2: 22% [E3].")


def test_following_metric_in_same_sentence_cannot_support_the_requested_measurement(evidence):
    evidence[2]["table_row"]["cells"][0]["value"] = "Reference model without augmentation"
    evidence[0]["text"] = "The reference model had an error rate of 17% and precision of 91%."
    scope = scope_table_answer(QUESTION, evidence)
    assert scope.supports("Overview: 17% [E1].\nTable 2: 22% [E3].")
    assert not scope.supports("Overview: 91% [E1].\nTable 2: 22% [E3].")


def test_ambiguous_abbreviation_does_not_establish_condition(evidence):
    attach_term_definitions([
        {"page_number": 1, "text": "Data augmentation (DA) and design analysis (DA)."},
        {"page_number": 4, "text": "", "table_rows": [evidence[3]["table_row"]]},
    ])
    assert not scope_table_answer(QUESTION, evidence).sources


def test_prefixed_units_and_qualifiers_are_kept_verbatim(evidence):
    evidence[2]["table_row"]["cells"][0]["value"] = "Reference model without augmentation"
    evidence[2]["table_row"]["cells"][1]["value"] = "$1.17/W dc"
    scope = scope_table_answer(QUESTION, evidence)
    assert scope.supports("Overview: 17% [E1].\nTable 2: $1.17/W dc [E3].")
    assert not scope.supports("Overview: 17% [E1].\nTable 2: $1.17/W ac [E3].")
    evidence[2]["table_row"]["cells"][1]["value"] = "1.17 MW"
    scope = scope_table_answer(QUESTION, evidence)
    assert scope.supports("Overview: 17% [E1].\nTable 2: 1.17 MW [E3].")
    assert not scope.supports("Overview: 17% [E1].\nTable 2: 1.17 mW [E3].")


def test_citation_returns_only_the_verified_cells(monkeypatch, evidence):
    evidence[2]["table_row"]["cells"][0]["value"] = "Reference model without augmentation"
    for index, source in enumerate(evidence, start=1):
        source.update(chunk_id=index, title="Study", page_end=source["page_start"])
    provider = SimpleNamespace(generate_json=lambda **_: json.dumps({
        "answer": "Overview: 17% [E1].\nTable 2: 22% [E3].", "abstained": False, "reason": None,
    }))
    monkeypatch.setattr("app.generation.answerer.get_generation_provider", lambda _: provider)
    answer = generate_answer(QUESTION, "retrieved context", evidence)
    assert "table_measurements" not in answer["citations"][0]
    assert answer["citations"][1]["table_measurements"] == [{"column": "ER Score", "value": "22%"}]
