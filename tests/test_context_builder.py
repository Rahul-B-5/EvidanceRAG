
import pytest

from app.generation.context_builder import build_evidence_context


def make_result(
    chunk_id=10,
    document_id=1,
    text="A research finding.",
    page_start=3,
    page_end=3,
):
    return {
        "chunk_id": chunk_id,
        "document_id": document_id,
        "title": "Research Paper",
        "filename": "research.pdf",
        "page_start": page_start,
        "page_end": page_end,
        "text": text,
        "rrf_score": 0.02,
    }


def test_builds_labeled_evidence():
    results = [make_result(), make_result(chunk_id=11, text="Another finding.")]

    context, evidence = build_evidence_context(results)

    assert len(evidence) == 2
    assert evidence[0]["evidence_id"] == "E1"
    assert evidence[1]["evidence_id"] == "E2"
    assert "[E1]" in context
    assert "[E2]" in context
    assert "Research Paper" in context


def test_skips_empty_passages():
    results = [
        make_result(text="   "),
        make_result(chunk_id=11, text="Useful evidence."),
    ]

    context, evidence = build_evidence_context(results)

    assert len(evidence) == 1
    assert evidence[0]["evidence_id"] == "E1"
    assert evidence[0]["chunk_id"] == 11
    assert "[E1]" in context
    assert "[E2]" not in context


def test_truncates_long_passages():
    long_text = "x" * 100
    _, evidence = build_evidence_context(
        [make_result(text=long_text)],
        max_chars_per_chunk=20,
    )

    assert evidence[0]["text"] == "x" * 20


def test_formats_page_ranges():
    context, evidence = build_evidence_context(
        [make_result(page_start=3, page_end=5)]
    )

    assert evidence[0]["page_start"] == 3
    assert evidence[0]["page_end"] == 5
    assert "Pages: 3-5" in context


def test_rejects_nonpositive_chunk_limit():
    with pytest.raises(ValueError, match="must be positive"):
        build_evidence_context([], max_chars_per_chunk=0)
