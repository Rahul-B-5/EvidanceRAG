
from app.core.config import get_settings


def chunk_pages(
    pages: list[dict[str, int | str]],
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
) -> list[dict[str, int | str]]:
    """
    Split page-wise extracted PDF text into overlapping chunks.

    Each chunk retains its index and original page range.
    Chunk boundaries are based on characters, not tokens.
    """
    settings = get_settings()

    size = chunk_size if chunk_size is not None else settings.chunk_size
    overlap = (
        chunk_overlap
        if chunk_overlap is not None
        else settings.chunk_overlap
    )

    if size <= 0:
        raise ValueError("chunk_size must be positive.")

    if not 0 <= overlap < size:
        raise ValueError("chunk_overlap must be non-negative and smaller than chunk_size.")

    # Sort pages and ignore empty or whitespace-only text.
    ordered_pages = sorted(pages, key=lambda page: int(page["page_number"]))

    segments = []
    for page in ordered_pages:
        page_number = int(page["page_number"])
        text = str(page["text"]).strip()

        if text:
            segments.append((page_number, text))

    if not segments:
        return []

    # Join page text while tracking the source page of each character.
    full_text_parts = []
    page_map = []
    previous_page = None

    for page_number, text in segments:
        if full_text_parts:
            full_text_parts.append("\n\n")
            page_map.extend([previous_page] * 2)

        full_text_parts.append(text)
        page_map.extend([page_number] * len(text))
        previous_page = page_number

    full_text = "".join(full_text_parts)

    chunks = []
    start = 0

    while start < len(full_text):
        end = min(start + size, len(full_text))

        # Prefer ending at a word boundary when one is nearby.
        if end < len(full_text):
            boundary = full_text.rfind(" ", start, end)
            if boundary > start:
                end = boundary

        chunk_text = full_text[start:end].strip()

        if chunk_text:
            chunks.append(
                {
                    "chunk_index": len(chunks),
                    "text": chunk_text,
                    "page_start": page_map[start],
                    "page_end": page_map[end - 1],
                }
            )

        if end >= len(full_text):
            break

        # Guarantee forward progress while preserving overlap.
        next_start = max(start + 1, end - overlap)

        # Avoid starting in the middle of a word.
        while (
            next_start < end
            and full_text[next_start] != " "
            and full_text[next_start - 1] != " "
        ):
            next_start += 1

        start = next_start

    return chunks
