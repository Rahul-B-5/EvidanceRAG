import importlib
import os
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import psycopg
import pymupdf
import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.ingestion import pipeline
from evaluation.database import isolated_database

api = importlib.import_module("app.api.main")
pytestmark = pytest.mark.skipif(os.getenv("EVIDENCERAG_INTEGRATION") != "1", reason="Requires PostgreSQL")


@pytest.fixture
def managed_fixture(tmp_path, monkeypatch):
    fixture = tmp_path / "source.pdf"
    with pymupdf.open() as pdf:
        pdf.new_page().insert_text((54, 54), "Synthetic source lifecycle test.")
        pdf.save(fixture)
    settings = get_settings().model_copy(update={"upload_dir": tmp_path / "uploads"})
    vector = [1.0] + [0.0] * (settings.embedding_dimensions - 1)
    monkeypatch.setattr(api, "get_settings", lambda: settings)
    monkeypatch.setattr(pipeline, "get_settings", lambda: settings)
    monkeypatch.setattr(pipeline, "embed_documents", lambda texts: [vector for _ in texts])
    with isolated_database() as (_, dsn):
        def connect():
            return psycopg.connect(dsn)

        monkeypatch.setattr(api, "get_connection", connect)
        monkeypatch.setattr(pipeline, "get_connection", connect)
        yield fixture, settings.upload_dir, connect


def test_delete_and_reimport_same_bytes_are_serialized(managed_fixture, monkeypatch):
    fixture, upload_dir, _ = managed_fixture
    first = pipeline.ingest_pdf(fixture)
    first_id = first["document_id"]
    delete_committed, allow_unlink, reimport_started = Event(), Event(), Event()
    original_unlink = api._delete_managed_source
    original_lock = pipeline.lock_source

    def pause_unlink(path):
        delete_committed.set()
        assert allow_unlink.wait(5)
        original_unlink(path)

    def observed_lock(conn, file_hash):
        reimport_started.set()
        original_lock(conn, file_hash)

    monkeypatch.setattr(api, "_delete_managed_source", pause_unlink)
    monkeypatch.setattr(pipeline, "lock_source", observed_lock)
    client = TestClient(api.app)
    with ThreadPoolExecutor(max_workers=2) as workers:
        removed = workers.submit(client.delete, f"/documents/{first_id}")
        try:
            assert delete_committed.wait(5)
            reimported = workers.submit(pipeline.ingest_pdf, fixture)
            assert reimport_started.wait(5)
            with pytest.raises(TimeoutError):
                reimported.result(timeout=0.25)
        finally:
            allow_unlink.set()
        assert removed.result(timeout=5).status_code == 204
        new = reimported.result(timeout=5)
    assert new["status"] == "ingested" and new["document_id"] != first_id
    assert client.get(f"/documents/{new['document_id']}/source").content == fixture.read_bytes()
    assert list(upload_dir.glob("*.pdf")) == [upload_dir / (pipeline.calculate_file_hash(fixture) + ".pdf")]


def test_failed_ingest_removes_only_a_new_unreferenced_copy(managed_fixture, monkeypatch):
    fixture, upload_dir, connect = managed_fixture

    def fail_chunks(*args, **kwargs):
        raise psycopg.DatabaseError("Simulated failed chunk insert")

    monkeypatch.setattr(pipeline, "insert_chunks", fail_chunks)
    with pytest.raises(psycopg.DatabaseError):
        pipeline.ingest_pdf(fixture)
    assert list(upload_dir.glob("*.pdf")) == []
    with connect() as conn:
        assert conn.execute("SELECT count(*) FROM documents").fetchone() == (0,)

    stored = pipeline.persist_source_pdf(fixture, file_hash=pipeline.calculate_file_hash(fixture), upload_dir=upload_dir)
    with pytest.raises(psycopg.DatabaseError):
        pipeline.ingest_pdf(fixture)
    assert stored.read_bytes() == fixture.read_bytes()
