from unittest.mock import Mock

from fastapi.testclient import TestClient

from app.api.main import app
from app.core.config import get_settings


def test_host_and_browser_origin_are_checked_before_dispatch(monkeypatch):
    ingest = Mock(return_value={"status":"ingested", "document_id":1})
    monkeypatch.setattr("app.api.main.ingest_pdf", ingest)
    client = TestClient(app)
    fixture = {"file": ("fixture.pdf", b"synthetic fixture", "application/pdf")}
    assert client.get("/health", headers={"Host":"unrecognized.example"}).status_code == 400
    assert client.post("/documents", files=fixture, headers={"Origin":"https://unrecognized.example"}).status_code == 403
    assert client.post("/documents", files=fixture, headers={"Origin":"null"}).status_code == 403
    assert client.post("/documents", files=fixture, headers={"Sec-Fetch-Site":"cross-site"}).status_code == 403
    ingest.assert_not_called()

    origin = get_settings().cors_origins.split(",")[0].strip()
    preflight = {"Origin":origin, "Access-Control-Request-Method":"POST", "Access-Control-Request-Headers":"Content-Type"}
    assert client.options("/documents", headers=preflight).status_code == 200
    assert client.options("/documents", headers={**preflight, "Host":"unrecognized.example"}).status_code == 400
    response = client.post("/documents", files=fixture, headers={"Origin":origin})
    assert response.status_code == 201
    assert response.headers["access-control-allow-origin"] == origin
    assert client.post("/documents", files=fixture, headers={"Origin":"http://testserver"}).status_code == 201
    assert client.post("/documents", files=fixture).status_code == 201
    assert ingest.call_count == 3


def test_ipv6_loopback_accepts_its_same_origin(monkeypatch):
    monkeypatch.setattr("app.api.main.ingest_pdf", lambda _: {"status":"ingested","document_id":1})
    response = TestClient(app, base_url="http://[::1]:80").post(
        "/documents", headers={"Origin":"http://[::1]"},
        files={"file": ("fixture.pdf", b"synthetic fixture", "application/pdf")},
    )
    assert response.status_code == 201
