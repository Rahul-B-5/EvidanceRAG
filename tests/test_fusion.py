
import pytest

from app.retrieval.fusion import reciprocal_rank_fusion


def result(chunk_id):
    return {
        "chunk_id": chunk_id,
        "document_id": 1,
        "text": f"Passage {chunk_id}",
    }


def test_fuses_rankings_from_multiple_retrievers():
    vector_results = [result(1), result(2)]
    keyword_results = [result(2), result(3)]

    fused = reciprocal_rank_fusion(
        [vector_results, keyword_results],
        k=60,
        top_k=3,
    )

    assert [item["chunk_id"] for item in fused] == [2, 1, 3]
    assert all(item["rrf_score"] > 0 for item in fused)


def test_duplicate_chunk_counts_once_per_list():
    normal = reciprocal_rank_fusion(
        [[result(1), result(2)]],
        k=60,
        top_k=2,
    )
    duplicated = reciprocal_rank_fusion(
        [[result(1), result(1), result(2)]],
        k=60,
        top_k=2,
    )

    normal_scores = {
        item["chunk_id"]: item["rrf_score"] for item in normal
    }
    duplicated_scores = {
        item["chunk_id"]: item["rrf_score"] for item in duplicated
    }

    assert duplicated_scores[1] == pytest.approx(normal_scores[1])
    assert duplicated_scores[2] == pytest.approx(normal_scores[2])


def test_respects_top_k():
    fused = reciprocal_rank_fusion(
        [[result(1), result(2), result(3)]],
        top_k=2,
    )

    assert len(fused) == 2


@pytest.mark.parametrize(
    ("k", "top_k"),
    [(0, 5), (-1, 5), (60, 0), (60, -1)],
)
def test_rejects_invalid_parameters(k, top_k):
    with pytest.raises(ValueError):
        reciprocal_rank_fusion([[result(1)]], k=k, top_k=top_k)
