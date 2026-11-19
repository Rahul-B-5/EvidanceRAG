"""Deterministic, evidence-first comparisons usable without a generation provider."""

from app.generation.context_builder import build_evidence_context
from app.retrieval.keyword import search_keyword


COMPARISON_FIELDS = {
    "methodology": "method OR approach OR architecture OR proposed OR model",
    "datasets": "dataset OR benchmark OR training OR testing OR split",
    "training": "optimizer OR learning OR loss OR epoch OR augmentation",
    "metrics": "metric OR accuracy OR precision OR recall OR f1 OR auc",
    "results": "result OR performance OR improvement OR baseline",
    "limitations": "limitation OR future OR challenge OR constraint",
}


def compare_documents(document_ids: list[int], *, passages_per_field: int = 2) -> dict:
    """Collect traceable comparison evidence for each requested paper.

    This intentionally reports ``missing`` when the local corpus does not
    contain a matching passage. It does not infer a field from an LLM.
    """
    if len(set(document_ids)) < 2:
        raise ValueError("Comparison requires at least two distinct documents.")
    if passages_per_field <= 0:
        raise ValueError("passages_per_field must be positive.")

    papers = []
    for document_id in document_ids:
        fields = {}
        title = None
        for field, query in COMPARISON_FIELDS.items():
            results = search_keyword(query, top_k=passages_per_field, document_id=document_id)
            _, evidence = build_evidence_context(results, max_chars_per_chunk=800)
            if evidence and title is None:
                title = evidence[0]["title"]
            fields[field] = {
                "status": "evidence_found" if evidence else "missing",
                "evidence": evidence,
            }
        papers.append({"document_id": document_id, "title": title, "fields": fields})

    return {
        "document_ids": document_ids,
        "fields": list(COMPARISON_FIELDS),
        "papers": papers,
        "notice": "Entries show retrieved source passages, not generated conclusions.",
    }
