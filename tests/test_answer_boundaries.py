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
