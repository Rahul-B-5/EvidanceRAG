from app.core.config import get_settings
from app.ingestion.pdf_extractor import ExtractedPage


def chunk_pages(
    pages: list[ExtractedPage],
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
) -> list[dict[str, int | str]]:
    """Split text into character windows anchored to a single physical PDF page."""
    settings = get_settings()
    size = chunk_size if chunk_size is not None else settings.chunk_size
    overlap = chunk_overlap if chunk_overlap is not None else settings.chunk_overlap

    if size <= 0:
        raise ValueError("chunk_size must be positive.")
    if not 0 <= overlap < size:
        raise ValueError("chunk_overlap must be non-negative and smaller than chunk_size.")

    chunks = []
    for page in sorted(pages, key=lambda item: int(item["page_number"])):
        page_number = int(page["page_number"])
        anchor: dict[str, int | str] = {"page_start": page_number, "page_end": page_number}
        if "section_title" in page:
            anchor["section_title"] = page["section_title"]
        text = str(page["text"]).strip()
        start = 0
        while start < len(text):
            end = min(start + size, len(text))
            if end < len(text) and not text[end].isspace():
                # Preserve whole words when there is room for overlap and forward progress.
                minimum = start + max(size // 2, overlap + 1)
                for boundary in range(end - 1, minimum - 1, -1):
                    if text[boundary].isspace():
                        end = boundary
                        break

            chunk_text = text[start:end].strip()
            if chunk_text:
                chunks.append({
                    "chunk_index": len(chunks),
                    "text": chunk_text,
                    **anchor,
                })
            if end == len(text):
                break

            next_start = max(start + 1, end - overlap)
            while next_start < end and not text[next_start - 1].isspace():
                next_start += 1
            while next_start < len(text) and text[next_start].isspace():
                next_start += 1
            start = next_start

        for row in page.get("table_rows", []):
            row_text = "Reconstructed table row: " + row
            if len(row_text) <= size:
                chunks.append({
                    "chunk_index": len(chunks),
                    "text": row_text,
                    **anchor,
                })

    return chunks
