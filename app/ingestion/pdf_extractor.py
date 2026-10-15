
from pathlib import Path

import pymupdf


def extract_pdf(pdf_path: str | Path) -> list[dict[str, int | str]]:
    """
    Extract text from a PDF one page at a time.

    Returns:
        A list of dictionaries containing the one-indexed page number
        and the extracted text for that page.
    """
    path = Path(pdf_path)

    if not path.exists():
        raise FileNotFoundError(f"PDF file not found: {path}")

    if not path.is_file():
        raise ValueError(f"Expected a PDF file, got: {path}")

    if path.suffix.lower() != ".pdf":
        raise ValueError(f"Expected a .pdf file, got: {path.name}")

    pages = []

    with pymupdf.open(path) as document:
        if document.is_encrypted:
            raise ValueError("Encrypted PDFs are not supported.")

        for page_number, page in enumerate(document, start=1):
            text = page.get_text("text").strip()

            pages.append(
                {
                    "page_number": page_number,
                    "text": text,
                }
            )

    return pages
