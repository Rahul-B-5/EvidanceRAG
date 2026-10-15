
def build_evidence_context(
    results: list[dict],
    max_chars_per_chunk: int = 2000,
) -> tuple[str, list[dict]]:
    """Format retrieved passages into labeled evidence for an LLM."""

    if max_chars_per_chunk <= 0:
        raise ValueError("max_chars_per_chunk must be positive.")

    evidence: list[dict] = []
    context_blocks: list[str] = []

    for result in results:
        text = (result.get("text") or "").strip()

        # Do not pass empty passages to the LLM.
        if not text:
            continue

        evidence_id = f"E{len(evidence) + 1}"
        passage = text[:max_chars_per_chunk]

        item = {
            "evidence_id": evidence_id,
            "chunk_id": result["chunk_id"],
            "document_id": result["document_id"],
            "title": result.get("title") or "Untitled document",
            "filename": result.get("filename"),
            "page_start": result["page_start"],
            "page_end": result["page_end"],
            "text": passage,
            "rrf_score": result.get("rrf_score"),
        }
        evidence.append(item)

        page_start = item["page_start"]
        page_end = item["page_end"]
        page_label = (
            str(page_start)
            if page_start == page_end
            else f"{page_start}-{page_end}"
        )

        context_blocks.append(
            f"[{evidence_id}]\n"
            f"Source: {item['title']}\n"
            f"Filename: {item['filename'] or 'Unknown'}\n"
            f"Pages: {page_label}\n"
            f"Passage:\n{passage}"
        )

    return "\n\n---\n\n".join(context_blocks), evidence
