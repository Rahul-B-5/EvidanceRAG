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
