from pathlib import Path

from app.ingestion.pipeline import calculate_file_hash, persist_source_pdf


def test_persist_source_pdf_creates_content_addressed_copy(tmp_path: Path):
    source = tmp_path / "paper.pdf"
    source.write_bytes(b"first version")
    uploads = tmp_path / "uploads"
    file_hash = calculate_file_hash(source)

    stored = persist_source_pdf(source, file_hash=file_hash, upload_dir=uploads)

    assert stored == uploads / f"{file_hash}.pdf"
    assert stored.read_bytes() == b"first version"


def test_persist_source_pdf_keeps_existing_content_addressed_copy(tmp_path: Path):
    source = tmp_path / "paper.pdf"
    source.write_bytes(b"source")
    uploads = tmp_path / "uploads"
    file_hash = calculate_file_hash(source)
    stored = persist_source_pdf(source, file_hash=file_hash, upload_dir=uploads)

    stored.write_bytes(b"canonical copy")
    source.write_bytes(b"different source at same path")

    result = persist_source_pdf(source, file_hash=file_hash, upload_dir=uploads)

    assert result == stored
    assert stored.read_bytes() == b"canonical copy"
