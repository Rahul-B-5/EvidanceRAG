from contextlib import nullcontext
from types import SimpleNamespace

from fastapi.testclient import TestClient
from psycopg import OperationalError

from app.api.main import app
from app.core.config import get_settings


client = TestClient(app)


def test_search_exposes_retrieval_result(monkeypatch):
    expected = {"query": "transformers", "results": [], "evidence": [], "context": "", "evidence_count": 0}

    def fake_retrieve(query, top_k=None, document_id=None):
        assert query == "transformers"
        assert top_k == 3
        assert document_id == 7
        return expected

    monkeypatch.setattr("app.api.main.retrieve_evidence", fake_retrieve)

    response = client.get("/search", params={"query": "transformers", "top_k": 3, "document_id": 7})

    assert response.status_code == 200
    assert response.json() == expected


def test_answer_returns_generated_answer_and_evidence(monkeypatch):
    retrieval = {"context": "[E1]", "evidence": [{"evidence_id": "E1"}]}
    generated = {"answer": "Supported [E1]", "abstained": False, "reason": None, "citations": []}

    monkeypatch.setattr("app.api.main.retrieve_evidence", lambda *args, **kwargs: retrieval)
    monkeypatch.setattr("app.api.main.generate_answer", lambda *args, **kwargs: generated)

    response = client.post("/answers", json={"query": "What happened?"})

    assert response.status_code == 200
    assert response.json() == {**generated, "evidence": retrieval["evidence"]}


def test_upload_rejects_non_pdf_without_ingesting():
    response = client.post(
        "/documents",
        files={"file": ("notes.txt", b"not a PDF", "text/plain")},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Only PDF files are supported."


def test_upload_preserves_safe_original_filename_for_ingestion(monkeypatch):
    received = {}

    def fake_ingest(path):
        received["filename"] = path.name
        received["exists_during_ingestion"] = path.exists()
        return {"status": "ingested", "document_id": 99}

    monkeypatch.setattr("app.api.main.ingest_pdf", fake_ingest)

    response = client.post(
        "/documents",
        files={"file": ("../../research.pdf", b"pdf bytes", "application/pdf")},
    )

    assert response.status_code == 201
    assert received == {
        "filename": "research.pdf",
        "exists_during_ingestion": True,
    }


def test_missing_document_and_conversation_return_not_found(monkeypatch):
    monkeypatch.setattr("app.api.main.get_connection", lambda: nullcontext(object()))
    monkeypatch.setattr("app.api.main.get_document", lambda *args: None)
    monkeypatch.setattr("app.api.main.get_document_source_path", lambda *args: None)
    monkeypatch.setattr("app.api.main.get_document_hash", lambda *args: None)
    monkeypatch.setattr("app.api.main.get_conversation", lambda *args: None)
    assert client.get("/documents/999999").status_code == 404
    assert client.get("/documents/999999/source").status_code == 404
    assert client.delete("/documents/999999").status_code == 404
    assert client.get("/conversations/999999").status_code == 404


def test_answer_without_provider_returns_service_unavailable(monkeypatch):
    monkeypatch.setattr(
        "app.api.main.retrieve_evidence",
        lambda *args, **kwargs: {"context": "[E1]", "evidence": [{"evidence_id": "E1"}]},
    )

    def unavailable(*args, **kwargs):
        raise RuntimeError("No generation provider is configured.")

    monkeypatch.setattr("app.api.main.generate_answer", unavailable)
    response = client.post("/answers", json={"query": "Question"})

    assert response.status_code == 503
    assert response.json()["detail"] == "No generation provider is configured."


def test_managed_pdf_range_supports_cross_origin_reader(monkeypatch, tmp_path):
    source = tmp_path / "synthetic.pdf"
    source.write_bytes(b"%PDF-1.7\nreader-byte-range-fixture")
    origins = get_settings().cors_origins
    origin = origins.split(",")[0].strip()
    monkeypatch.setattr("app.api.main.get_settings", lambda: SimpleNamespace(upload_dir=tmp_path))
    monkeypatch.setattr("app.api.main.get_connection", lambda: nullcontext(object()))
    monkeypatch.setattr("app.api.main.get_document_source_path", lambda *args: str(source))
    response = client.get("/documents/1/source", headers={"Origin": origin, "Range": "bytes=0-7"})
    assert response.status_code == 206
    assert response.content == source.read_bytes()[:8]
    assert response.headers["content-range"] == f"bytes 0-7/{source.stat().st_size}"
    assert response.headers["accept-ranges"] == "bytes"
    assert response.headers["access-control-allow-origin"] == origin
    assert "content-range" in response.headers["access-control-expose-headers"].lower()


def test_database_connection_failure_is_sanitized(monkeypatch, caplog):
    def fail_connection():
        raise OperationalError("Sensitive driver detail")

    monkeypatch.setattr("app.api.main.get_connection", fail_connection)
    response = client.get("/documents")
    assert response.status_code == 503
    assert response.json() == {"detail": "Database is unavailable."}
    assert "Sensitive driver detail" not in caplog.text
