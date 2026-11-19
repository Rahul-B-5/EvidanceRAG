import pytest

from research.comparison import compare_documents


def test_comparison_marks_missing_fields_and_keeps_evidence(monkeypatch):
    def fake_search(query, top_k, document_id):
        if query.startswith("method") and document_id == 1:
            return [{"chunk_id": 7, "document_id": 1, "title": "Paper one", "filename": "one.pdf", "page_start": 2, "page_end": 2, "text": "A method passage."}]
        return []

    monkeypatch.setattr("research.comparison.search_keyword", fake_search)
    result = compare_documents([1, 2])

    assert result["papers"][0]["fields"]["methodology"]["status"] == "evidence_found"
    assert result["papers"][0]["fields"]["methodology"]["evidence"][0]["chunk_id"] == 7
    assert result["papers"][1]["fields"]["methodology"]["status"] == "missing"


def test_comparison_requires_distinct_documents():
    with pytest.raises(ValueError, match="distinct"):
        compare_documents([1, 1])
