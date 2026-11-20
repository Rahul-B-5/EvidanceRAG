import os
import subprocess
import sys

import psycopg
import pymupdf
import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.core.config import get_settings
from app.ingestion import jobs, pipeline
from evaluation.browser import fixture_pdf
from evaluation.database import isolated_database

pytestmark = pytest.mark.skipif(os.getenv("EVIDENCERAG_INTEGRATION") != "1", reason="Requires PostgreSQL")


@pytest.fixture
def import_fixture(tmp_path, monkeypatch):
    with isolated_database() as (_, dsn):
        def connect():
            return psycopg.connect(dsn)

        config = get_settings().model_copy(update={"upload_dir":tmp_path / "uploads"})
        monkeypatch.setattr(jobs, "get_settings", lambda: config)
        monkeypatch.setattr(pipeline, "get_settings", lambda: config)
        monkeypatch.setattr(jobs, "get_connection", connect)
        monkeypatch.setattr(pipeline, "get_connection", connect)
        fixture = tmp_path / "job-fixture.pdf"
        fixture_pdf(fixture)
        yield fixture, config.upload_dir, connect, dsn


def upload(client, fixture):
    return client.post("/import-jobs", files={"file":(fixture.name,fixture.read_bytes(),"application/pdf")})


def test_worker_restart_recovers_input_after_paper_commit_without_duplicate(import_fixture):
    fixture, storage, connect, dsn = import_fixture
    client = TestClient(app)
    queued = upload(client, fixture)
    assert queued.status_code == 202
    job = queued.json()
    assert job["state"] == "queued"
    env = {**os.environ, "DATABASE_URL":dsn, "UPLOAD_DIR":str(storage), "EMBEDDING_DIMENSIONS":"3"}
    crashed = subprocess.run([sys.executable,"-c","""
import os
from app.ingestion import jobs, pipeline
pipeline.embed_documents = lambda texts: [[1.,0.,0.] for _ in texts]
def exit_after_commit(path):
    assert pipeline.ingest_pdf(path)["status"] == "ingested"
    os._exit(23)
jobs.ingest_pdf = exit_after_commit
jobs.process_next_job()
"""], env=env, capture_output=True, timeout=25, check=False)
    assert crashed.returncode == 23
    assert client.get("/import-jobs").json()["jobs"][0]["state"] == "indexing"
    with connect() as conn:
        original_id, stored_path = conn.execute("SELECT id,stored_path FROM documents").fetchone()
        assert conn.execute("SELECT count(*) FROM chunks").fetchone() == (1,)
    assert (storage / ".imports" / job["id"] / fixture.name).is_file()
    assert jobs.process_next_job()
    result = client.get("/import-jobs").json()["jobs"][0]
    assert (result["state"],result["attempts"],result["document_id"]) == ("duplicate",2,original_id)
    assert not (storage / ".imports" / job["id"]).exists()
    with connect() as conn:
        assert conn.execute("SELECT id,stored_path FROM documents").fetchall() == [(original_id,stored_path)]
        assert conn.execute("SELECT count(*) FROM chunks").fetchone() == (1,)


def test_retry_uses_retained_file_and_malformed_pdf_cannot_be_retried(import_fixture, monkeypatch):
    fixture, storage, _, _ = import_fixture
    client = TestClient(app)
    job = upload(client, fixture).json()

    def unavailable(_path):
        raise RuntimeError("Synthetic temporary error.")

    monkeypatch.setattr(jobs,"ingest_pdf",unavailable)
    assert jobs.process_next_job()
    failed = client.get("/import-jobs").json()["jobs"][0]
    assert failed["state"] == "failed" and failed["retryable"]
    assert (storage / ".imports" / job["id"] / fixture.name).is_file()
    assert client.post(f"/import-jobs/{job['id']}/retry").json()["state"] == "queued"
    assert client.post(f"/import-jobs/{job['id']}/retry").status_code == 409
    monkeypatch.setattr(jobs,"ingest_pdf",pipeline.ingest_pdf)
    dimension = get_settings().embedding_dimensions
    monkeypatch.setattr(pipeline, "embed_documents", lambda texts: [[1.] + [0.] * (dimension-1) for _ in texts])
    assert jobs.process_next_job()
    assert client.get("/import-jobs").json()["jobs"][0]["state"] == "imported"

    invalid = client.post("/import-jobs", files={"file":("invalid.pdf",b"not a PDF","application/pdf")}).json()
    assert jobs.process_next_job()
    result = next(row for row in client.get("/import-jobs").json()["jobs"] if row["id"] == invalid["id"])
    assert result["state"] == "failed" and not result["retryable"]
    assert not (storage / ".imports" / invalid["id"]).exists()
    assert client.post(f"/import-jobs/{invalid['id']}/retry").status_code == 409


def test_import_persists_individual_physical_pages(import_fixture, monkeypatch):
    fixture, _, connect, _ = import_fixture
    source = fixture.with_name("separate-pages.pdf")
    with pymupdf.open() as pdf:
        pdf.new_page().insert_text((54, 54), "The first page defines the model.")
        pdf.new_page()
        pdf.new_page().insert_text((54, 54), "The third page reports the results.")
        pdf.save(source)

    dimension = get_settings().embedding_dimensions
    monkeypatch.setattr(pipeline, "embed_documents", lambda texts: [[1.] + [0.] * (dimension - 1) for _ in texts])
    client = TestClient(app)
    assert upload(client, source).status_code == 202
    assert jobs.process_next_job()
    assert client.get("/import-jobs").json()["jobs"][0]["state"] == "imported"
    with connect() as conn:
        assert conn.execute("SELECT text, page_start, page_end FROM chunks ORDER BY chunk_index").fetchall() == [
            ("The first page defines the model.", 1, 1),
            ("The third page reports the results.", 3, 3),
        ]
