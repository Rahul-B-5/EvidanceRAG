
import hashlib
from pathlib import Path

import pymupdf

from app.core.config import get_settings
from app.db.connection import get_connection
from app.db.repository import insert_chunks, insert_document
from app.ingestion.chunker import chunk_pages
from app.ingestion.pdf_extractor import extract_pdf
from app.retrieval.embeddings import embed_documents


def calculate_file_hash(file_path: Path) -> str:
    """Calculate a SHA-256 hash without loading the whole PDF into memory."""
    sha256 = hashlib.sha256()

    with file_path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            sha256.update(block)

    return sha256.hexdigest()


def extract_metadata(file_path: Path) -> dict:
    """Extract basic metadata, falling back to the filename when necessary."""
    with pymupdf.open(file_path) as pdf:
        metadata = pdf.metadata or {}

    title = (metadata.get("title") or "").strip()

# Some PDFs contain a software-generated title instead of the paper title.
    if (
        not title
        or title.lower().startswith("microsoft word -")
        or title.lower() in {"untitled", "document"}
    ):
        title = file_path.stem.replace("_", " ").strip()

    authors_text = (metadata.get("author") or "").strip()
    authors = [author.strip() for author in authors_text.split(",") if author.strip()]

    return {
        "title": title,
        "authors": authors,
        "publication_year": None,
    }


def ingest_pdf(file_path: str | Path) -> dict:
    """
    Extract, chunk, embed, and store a PDF.

    Duplicate files are identified using their SHA-256 hash.
    Document and chunk inserts share a database transaction.
    """
    settings = get_settings()
    path = Path(file_path).expanduser().resolve()

    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"PDF file not found: {path}")

    if path.suffix.lower() != ".pdf":
        raise ValueError("Only PDF files are supported.")

    max_bytes = settings.max_upload_mb * 1024 * 1024
    if path.stat().st_size > max_bytes:
        raise ValueError(
            f"PDF exceeds the configured {settings.max_upload_mb} MB limit."
        )

    file_hash = calculate_file_hash(path)

    # Quick duplicate check before spending time generating embeddings.
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT id FROM documents WHERE file_hash = %s",
            (file_hash,),
        ).fetchone()

    if existing is not None:
        return {
            "status": "already_exists",
            "document_id": existing[0],
            "filename": path.name,
            "chunks_created": 0,
        }

    pages = extract_pdf(path)
    chunks = chunk_pages(pages)

    if not chunks:
        raise ValueError(
            "No extractable text was found in this PDF. "
            "Scanned PDFs may require OCR."
        )

    embeddings = embed_documents([chunk["text"] for chunk in chunks])
    metadata = extract_metadata(path)

    # The connection context commits on success and rolls back on error.
    with get_connection() as conn:
        document_id, created = insert_document(
            conn,
            title=metadata["title"],
            authors=metadata["authors"],
            publication_year=metadata["publication_year"],
            filename=path.name,
            file_hash=file_hash,
        )

        # Another process may have ingested the same PDF concurrently.
        if not created:
            return {
                "status": "already_exists",
                "document_id": document_id,
                "filename": path.name,
                "chunks_created": 0,
            }

        chunks_created = insert_chunks(
            conn,
            document_id=document_id,
            chunks=chunks,
            embeddings=embeddings,
        )

    return {
        "status": "ingested",
        "document_id": document_id,
        "filename": path.name,
        "pages_extracted": len(pages),
        "chunks_created": chunks_created,
    }
