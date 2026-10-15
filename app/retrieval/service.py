
from app.generation.context_builder import build_evidence_context
from app.retrieval.fusion import search_hybrid


def retrieve_evidence(
    query: str,
    top_k: int | None = None,
    document_id: int | None = None,
    candidate_k: int = 20,
    rrf_k: int = 60,
) -> dict:
    """Retrieve relevant passages and prepare their evidence context."""

    if not query.strip():
        raise ValueError("Query must not be empty.")

    results = search_hybrid(
        query=query,
        top_k=top_k,
        document_id=document_id,
        candidate_k=candidate_k,
        rrf_k=rrf_k,
    )

    context, evidence = build_evidence_context(results)

    return {
        "query": query,
        "results": results,
        "context": context,
        "evidence": evidence,
        "evidence_count": len(evidence),
    }
