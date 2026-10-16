
from app.retrieval.keyword import search_keyword
from app.retrieval.vector import search_vector


def reciprocal_rank_fusion(
    result_lists: list[list[dict]],
    k: int = 60,
    top_k: int = 5,
) -> list[dict]:
    """
    Combine ranked retrieval results using Reciprocal Rank Fusion.

    Each result must contain a stable chunk_id. Ranks are one-indexed.
    """
    if k <= 0:
        raise ValueError("k must be positive.")

    if top_k <= 0:
        raise ValueError("top_k must be positive.")

    fused: dict[int, dict] = {}
    scores: dict[int, float] = {}

    for results in result_lists:
        seen_in_list: set[int] = set()


        rank = 0

        for result in results:
            chunk_id = result["chunk_id"]

            # Ignore duplicates without penalizing later unique results.
            if chunk_id in seen_in_list:
                continue

            seen_in_list.add(chunk_id)
            rank += 1

            scores[chunk_id] = (
                scores.get(chunk_id, 0.0) + 1.0 / (k + rank)
            )


            if chunk_id not in fused:
                fused[chunk_id] = dict(result)

    ranked = []

    for chunk_id, result in fused.items():
        item = dict(result)
        item["rrf_score"] = scores[chunk_id]
        ranked.append(item)

    ranked.sort(
        key=lambda item: (-item["rrf_score"], item["chunk_id"])
    )

    return ranked[:top_k]


def search_hybrid(
    query: str,
    top_k: int | None = None,
    document_id: int | None = None,
    candidate_k: int = 20,
    rrf_k: int = 60,
) -> list[dict]:
    """
    Retrieve candidates using vector and keyword search, then fuse rankings.
    """
    if not query.strip():
        raise ValueError("Search query must not be empty.")

    if candidate_k <= 0:
        raise ValueError("candidate_k must be positive.")

    if rrf_k <= 0:
        raise ValueError("rrf_k must be positive.")

    vector_results = search_vector(
        query,
        top_k=candidate_k,
        document_id=document_id,
    )

    keyword_results = search_keyword(
        query,
        top_k=candidate_k,
        document_id=document_id,
    )

    settings_top_k = top_k
    if settings_top_k is None:
        from app.core.config import get_settings
        settings_top_k = get_settings().retrieval_top_k

    if settings_top_k <= 0:
        raise ValueError("top_k must be positive.")

    return reciprocal_rank_fusion(
        [vector_results, keyword_results],
        k=rrf_k,
        top_k=settings_top_k,
    )
