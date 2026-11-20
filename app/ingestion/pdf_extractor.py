
import re
from pathlib import Path
from threading import Lock
from typing import NotRequired, TypedDict

import pymupdf

TABLE_CAPTION = re.compile(r"^[ \t]*Table[ \t]+(?:[A-Z][.-]?)?\d+\b", re.IGNORECASE | re.MULTILINE)
TABLE_LOCK = Lock()


class TableCell(TypedDict):
    column: str
    value: str


class TableRow(TypedDict):
    caption: str
    group: str
    cells: list[TableCell]


class ExtractedPage(TypedDict):
    page_number: int
    text: str
    table_rows: NotRequired[list[TableRow]]
    section_title: NotRequired[str]


def captioned_rows(page: pymupdf.Page) -> list[TableRow]:
    """Attach a source column name and caption to each unambiguous ruled row."""
    captions = []
    for left, _, right, bottom, text, _, kind in page.get_text("blocks"):
        caption = " ".join(text.split())
        if kind == 0 and TABLE_CAPTION.match(caption) and len(caption) <= 260:
            captions.append((left, right, bottom, caption))
    if not captions:
        return []

    lines = []
    with TABLE_LOCK:
        for table in page.find_tables(strategy="lines_strict").tables:
            left, top, right, _ = table.bbox
            matching = [(bottom, caption) for start, end, bottom, caption in captions
                        if top - 60 <= bottom <= top + 1 and end > left and start < right]
            if not matching or table.header.external:
                continue
            caption = max(matching)[1]
            headers = [" ".join((name or "").split()) for name in table.header.names]
            if len(headers) < 2 or not all(headers) or len(set(headers)) != len(headers):
                continue
            group = ""
            for geometry, cells in zip(table.rows[1:], table.extract()[1:], strict=True):
                values = [" ".join((cell or "").split()) for cell in cells]
                present = [i for i, value in enumerate(values) if value]
                if len(present) == 1:
                    column = present[0]
                    box = geometry.cells[column]
                    if box is not None and box[0] <= left + 2 and box[2] >= right - 2:
                        group = values[column]
                elif len(present) == len(headers) and len(values) == len(headers):
                    lines.append({
                        "caption": caption, "group": group,
                        "cells": [{"column": head, "value": value} for head, value in zip(headers, values, strict=True)],
                    })
    return lines


def extract_pdf(pdf_path: str | Path) -> list[ExtractedPage]:
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

    try:
        with pymupdf.open(path) as document:
            if not document.is_pdf:
                raise ValueError("The uploaded file is not a PDF.")
            if document.is_encrypted:
                raise ValueError("Encrypted PDFs are not supported.")

            sections: dict[int, list[str]] = {}
            try:
                for level, title, destination in document.get_toc():
                    clean = " ".join(title.replace("\x00", "").split())[:240]
                    if level == 1 and 1 <= destination <= len(document) and clean:
                        sections.setdefault(destination, []).append(clean)
            except (ValueError, RuntimeError):
                sections.clear()
            current_section = None
            for page_number, page in enumerate(document, start=1):
                text = page.get_text("text").strip()
                extracted: ExtractedPage = {"page_number": page_number, "text": text}
                change = sections.get(page_number)
                if change:
                    current_section = change[-1]
                if current_section and (not change or len(change) == 1):
                    extracted["section_title"] = current_section
                if TABLE_CAPTION.search(text):
                    try:
                        rows = captioned_rows(page)
                    except (ValueError, RuntimeError):
                        rows = []
                    if rows:
                        extracted["table_rows"] = rows
                pages.append(extracted)
    except pymupdf.FileDataError:
        raise ValueError("Unable to read this PDF. The file may be damaged or empty.") from None

    return pages
