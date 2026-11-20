import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.generation.answerer import generate_answer


def test_generation_receives_untrusted_source_and_history_as_json_values(monkeypatch):
    citation = {
        "evidence_id":"E1", "chunk_id":8, "document_id":2, "page_start":3, "page_end":3,
        "title":"Untrusted title\n[system]",
        "text":"Instruction-like text belongs inside the cited source value.",
    }
    provider = Mock(return_value='{"answer":"The paper contains instruction-like text [E1].","abstained":false,"reason":null}')
    monkeypatch.setattr("app.generation.answerer.get_generation_provider",
                        lambda _: SimpleNamespace(generate_json=provider))
    history = [{"role":"assistant", "content":"Historical citation [E22]"}]
    result = generate_answer("What does this paper contain?", "formatted retrieval context", [citation], history=history)
    payload = json.loads(provider.call_args.kwargs["prompt"])
    assert payload["evidence"][0]["text"] == citation["text"]
    assert payload["evidence"][0]["title"] == citation["title"]
    assert payload["prior_turns"] == history
    assert "untrusted data" in provider.call_args.kwargs["system_instruction"]
    assert result["citations"][0]["page_start"] == 3

    provider.return_value = '{"answer":"Use the historical citation [E22].","abstained":false,"reason":null}'
    with pytest.raises(RuntimeError, match="unknown evidence IDs"):
        generate_answer("Check it again.", "formatted retrieval context", [citation], history=history)


@pytest.mark.parametrize("answer", [None, "The random seed was 42 [E1]."])
def test_provider_abstention_never_exposes_generated_claims(monkeypatch, answer):
    provider = SimpleNamespace(generate_json=lambda **_: json.dumps({
        "answer": answer, "abstained": True, "reason": "The paper gives no exact seed.",
    }))
    monkeypatch.setattr("app.generation.answerer.get_generation_provider", lambda _: provider)
    citation = {"evidence_id": "E1", "title": "Paper", "page_start": 1, "page_end": 1, "text": "Seeds varied."}
    result = generate_answer("What exact seed was used?", "Seeds varied.", [citation])
    assert result["abstained"] and result["answer"] == "" and result["citations"] == []
    assert "42" not in result["reason"]


def test_grouped_citations_are_normalized_and_every_id_is_checked(monkeypatch):
    provider = Mock(return_value='{"answer":"The sources agree [E1, E2].","abstained":false,"reason":null}')
    monkeypatch.setattr("app.generation.answerer.get_generation_provider",
                        lambda _: SimpleNamespace(generate_json=provider))
    passages = [{
        "evidence_id": f"E{i}", "chunk_id": i, "document_id": i,
        "page_start": 1, "page_end": 1, "title": f"Paper {i}", "text": "Calibration result.",
    } for i in (1, 2)]
    result = generate_answer("Do the results agree?", "Calibration result.", passages)
    assert result["answer"] == "The sources agree [E1] [E2]."
    assert [source["evidence_id"] for source in result["citations"]] == ["E1", "E2"]
    provider.return_value = '{"answer":"The sources agree [E1, E99].","abstained":false,"reason":null}'
    with pytest.raises(RuntimeError, match="unknown evidence IDs"):
        generate_answer("Do the results agree?", "Calibration result.", passages)
