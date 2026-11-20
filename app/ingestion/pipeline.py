
import hashlib
import logging
import os
import re
import shutil
import uuid
from pathlib import Path

import pymupdf
from psycopg import Connection, Error

from app.core.config import get_settings
from app.db.connection import get_connection
from app.db.repository import insert_chunks, insert_document
from app.db.source_lock import lock_source
from app.ingestion.chunker import chunk_pages
from app.ingestion.pdf_extractor import extract_pdf
from app.retrieval.embeddings import embed_documents

logger = logging.getLogger(__name__)


def calculate_file_hash(file_path: Path) -> str:
    """Calculate a SHA-256 hash without loading the whole PDF into memory."""
    sha256 = hashlib.sha256()

    with file_path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            sha256.update(block)

    return sha256.hexdigest()


def persist_source_pdf(
    source_path: Path,
    *,
    file_hash: str,
    upload_dir: Path,
) -> Path:
    """Store an immutable, content-addressed copy of an imported PDF.

    The copy is written to a sibling temporary file and atomically renamed, so
    a partial upload is never exposed as a reusable document source.
    """
    if not re.fullmatch(r"[0-9a-f]{64}", file_hash):
        raise ValueError("Invalid source hash.")
    upload_dir = upload_dir.resolve()
    upload_dir.mkdir(parents=True, exist_ok=True)
    destination = upload_dir / f"{file_hash}.pdf"

    if destination.exists():
        if destination.is_symlink() or calculate_file_hash(destination) != file_hash:
            raise ValueError("Stored source failed its integrity check.")
        return destination

    temporary = upload_dir / f".{file_hash}.{uuid.uuid4().hex}.tmp"
    try:
        shutil.copyfile(source_path, temporary)
        if calculate_file_hash(temporary) != file_hash:
            raise ValueError("Source changed during import; retry the upload.")
        with temporary.open("rb+") as copied_file:
            copied_file.flush()
            os.fsync(copied_file.fileno())
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()

    return destination


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


def discard_failed_publication(conn: Connection, path: Path) -> None:
    """Remove a new copy only if the database confirms no document uses it."""
    try:
        with conn.transaction():
            referenced = conn.execute(
                "SELECT EXISTS(SELECT 1 FROM documents WHERE stored_path = %s)", (str(path),)
            ).fetchone()[0]
        if not referenced:
            path.unlink(missing_ok=True)
    except (Error, OSError) as exc:
        logger.warning("Managed source publication cleanup deferred (%s).", type(exc).__name__)


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

    with get_connection() as conn:
        lock_source(conn, file_hash)
        with conn.transaction():
            existing = conn.execute("SELECT id FROM documents WHERE file_hash = %s", (file_hash,)).fetchone()

        if existing:
            # Only byte-identical uploads can restore legacy source links.
            try:
                with pymupdf.open(path) as pdf:
                    if not pdf.is_pdf or pdf.is_encrypted:
                        raise ValueError("Only readable, unencrypted PDFs can restore a source.")
                    page_count = len(pdf)
            except pymupdf.FileDataError:
                raise ValueError("Unable to read this PDF. The file may be damaged or empty.") from None
        else:
            pages = extract_pdf(path)
            chunks = chunk_pages(pages)
            if not chunks:
                raise ValueError("No extractable text was found in this PDF. Scanned PDFs may require OCR.")
            embeddings = embed_documents([chunk["text"] for chunk in chunks])
            metadata = extract_metadata(path)
            page_count = len(pages)

        canonical = settings.upload_dir.resolve() / f"{file_hash}.pdf"
        new_source = not canonical.exists()
        stored_path = persist_source_pdf(path, file_hash=file_hash, upload_dir=settings.upload_dir)
        try:
            with conn.transaction():
                if existing:
                    document_id, created = existing[0], False
                else:
                    document_id, created = insert_document(
                        conn, **metadata, filename=path.name, file_hash=file_hash,
                        stored_path=str(stored_path), file_size_bytes=stored_path.stat().st_size,
                        page_count=page_count,
                    )
                if not created:
                    conn.execute("""
                        UPDATE documents SET stored_path = %s, file_size_bytes = %s, page_count = %s
                        WHERE id = %s AND file_hash = %s
                    """, (str(stored_path), stored_path.stat().st_size, page_count, document_id, file_hash))
                    return {"status": "already_exists", "document_id": document_id, "filename": path.name, "chunks_created": 0}
                chunks_created = insert_chunks(conn, document_id=document_id, chunks=chunks, embeddings=embeddings)
        except Exception:
            if new_source:
                discard_failed_publication(conn, stored_path)
            raise

        return {"status": "ingested", "document_id": document_id, "filename": path.name,
                "pages_extracted": page_count, "chunks_created": chunks_created}
