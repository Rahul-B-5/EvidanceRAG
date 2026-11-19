from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock

import pymupdf

from app.ingestion import pipeline


def test_duplicate_restores_source_without_regenerating_embeddings(tmp_path, monkeypatch):
    original = tmp_path / "paper.pdf"
    with pymupdf.open() as pdf:
        pdf.new_page().insert_text((72, 72), "Source restoration test")
        pdf.save(original)
    conn = Mock()
    conn.execute.return_value.fetchone.return_value = (42,)
    monkeypatch.setattr(pipeline, "get_connection", lambda: nullcontext(conn))
    monkeypatch.setattr(pipeline, "get_settings", lambda: SimpleNamespace(
        upload_dir=tmp_path / "uploads", max_upload_mb=25,
    ))
    embed = Mock(side_effect=AssertionError("Duplicates must not be re-embedded"))
    monkeypatch.setattr(pipeline, "embed_documents", embed)

    result = pipeline.ingest_pdf(original)

    assert result["status"] == "already_exists"
    assert result["document_id"] == 42
    assert result["chunks_created"] == 0
    embed.assert_not_called()
    params = conn.execute.call_args.args[1]
    assert params[2:] == (1, 42, pipeline.calculate_file_hash(original))
    assert (tmp_path / "uploads" / f"{params[-1]}.pdf").read_bytes() == original.read_bytes()
