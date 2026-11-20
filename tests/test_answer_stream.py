import asyncio
import json
from threading import Event

from fastapi.testclient import TestClient

from app.api.answer_stream import AnswerStreamCancelled, stream_answer
from app.api.main import app


def test_stream_delivers_progress_and_final_validated_response(monkeypatch):
    def exchange(request, progress):
        progress("retrieving")
        progress("generating")
        progress("saving")
        return {"answer": "Verified [E1]", "citations": [{"evidence_id": "E1"}]}

    monkeypatch.setattr("app.api.main.answer_exchange", exchange)
    response = TestClient(app).post("/answers/stream", json={"query": "What is reported?"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")
    assert response.headers["cache-control"] == "no-store"
    events = [json.loads(line) for line in response.text.splitlines()]
    assert [event["phase"] for event in events[:-1]] == ["retrieving", "generating", "saving"]
    assert events[-1]["type"] == "answer"
    assert events[-1]["result"]["citations"] == [{"evidence_id": "E1"}]


def test_stream_error_never_returns_unvalidated_text():
    response = TestClient(app).post("/answers/stream", json={"query": " "})
    assert [json.loads(line) for line in response.text.splitlines()] == [
        {"type": "error", "status": 422, "detail": "Query must not be empty."},
    ]


def test_asgi_disconnect_cancels_exchange_before_commit():
    release_provider = Event()
    worker_done = Event()
    cancelled = Event()

    def exchange(progress):
        try:
            progress("generating")
            assert release_provider.wait(timeout=2)
            progress("saving")
            raise AssertionError("The disconnected exchange was allowed to save")
        except AnswerStreamCancelled:
            cancelled.set()
            raise
        finally:
            worker_done.set()

    async def exercise():
        disconnect = asyncio.Event()

        async def receive():
            await disconnect.wait()
            return {"type": "http.disconnect"}

        async def send(message):
            body = message.get("body", b"")
            if body and json.loads(body).get("phase") == "generating":
                disconnect.set()

        response = stream_answer(exchange)
        await asyncio.wait_for(response({"type": "http", "asgi": {"spec_version": "2.3"}}, receive, send), timeout=2)
        release_provider.set()
        assert await asyncio.to_thread(worker_done.wait, 2)
        assert cancelled.is_set()

    asyncio.run(exercise())
