from pathlib import Path
import pytest

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

    result = persist_source_pdf(source, file_hash=file_hash, upload_dir=uploads)

    assert result == stored
    assert stored.read_bytes() == b"source"


def test_rejects_changed_source_and_cleans_temporary_copy(tmp_path):
    source = tmp_path / "paper.pdf"
    source.write_bytes(b"original")
    digest = calculate_file_hash(source)
    source.write_bytes(b"changed")
    with pytest.raises(ValueError, match="changed during import"):
        persist_source_pdf(source, file_hash=digest, upload_dir=tmp_path / "uploads")
    assert list((tmp_path / "uploads").iterdir()) == []


def test_rejects_corrupt_existing_source_without_overwriting_it(tmp_path):
    source = tmp_path / "paper.pdf"
    source.write_bytes(b"original")
    digest = calculate_file_hash(source)
    stored = persist_source_pdf(source, file_hash=digest, upload_dir=tmp_path / "uploads")
    stored.write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="integrity"):
        persist_source_pdf(source, file_hash=digest, upload_dir=tmp_path / "uploads")
    assert stored.read_bytes() == b"corrupt"


def test_rejects_path_in_hash(tmp_path):
    with pytest.raises(ValueError, match="Invalid source hash"):
        persist_source_pdf(tmp_path / "source", file_hash="../escape", upload_dir=tmp_path)
