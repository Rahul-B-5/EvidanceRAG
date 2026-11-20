"""Stream Assistant progress while keeping generated text behind validation."""

import asyncio
import json
import logging
from collections.abc import AsyncIterator, Callable
from threading import BoundedSemaphore, Event, Lock
from uuid import UUID

from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from fastapi.encoders import jsonable_encoder

logger = logging.getLogger(__name__)
_slots = BoundedSemaphore(4)
_heartbeat_seconds = 2
_requests: dict[UUID, Event] = {}
_request_lock = Lock()


def cancel_answer(request_id: UUID) -> bool:
    with _request_lock:
        event = _requests.get(request_id)
        if event is None:
            return False
        event.set()
        return True


class AnswerStreamCancelled(Exception):
    """The client stopped listening before the exchange committed."""


def stream_answer(run: Callable[[Callable[[str], None]], dict], request_id: UUID | None = None) -> StreamingResponse:
    async def events() -> AsyncIterator[bytes]:
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[dict] = asyncio.Queue()
        cancelled = Event()
        if request_id is not None:
            with _request_lock:
                if request_id in _requests:
                    raise HTTPException(409, "Answer request identifier is already active.")
                _requests[request_id] = cancelled

        def emit(event: dict) -> None:
            if not cancelled.is_set():
                loop.call_soon_threadsafe(queue.put_nowait, event)

        def progress(phase: str) -> None:
            if cancelled.is_set():
                raise AnswerStreamCancelled
            if phase:
                emit({"type": "progress", "phase": phase})

        def produce() -> None:
            if not _slots.acquire(blocking=False):
                emit({"type": "error", "status": 503, "detail": "Assistant is busy. Retry shortly."})
                if request_id is not None:
                    with _request_lock:
                        _requests.pop(request_id, None)
                return
            try:
                progress("")
                emit({"type": "answer", "result": run(progress)})
            except AnswerStreamCancelled:
                return
            except HTTPException as exc:
                emit({"type": "error", "status": exc.status_code, "detail": exc.detail})
            except Exception as exc:
                logger.error("Assistant exchange failed (%s)", type(exc).__name__)
                emit({"type": "error", "status": 500, "detail": "Unable to finish the answer. Retry the question."})
            finally:
                _slots.release()
                if request_id is not None:
                    with _request_lock:
                        _requests.pop(request_id, None)

        worker = asyncio.create_task(asyncio.to_thread(produce))
        try:
            while True:
                if cancelled.is_set():
                    yield (json.dumps({"type": "error", "status": 409, "detail": "Answer request cancelled."}) + "\n").encode()
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=_heartbeat_seconds)
                except TimeoutError:
                    event = {"type": "heartbeat"}
                yield (json.dumps(jsonable_encoder(event), ensure_ascii=False) + "\n").encode()
                if event["type"] in {"answer", "error"}:
                    break
        finally:
            cancelled.set()
            # Running synchronous provider calls stop at their configured timeout.
            # Their worker observes cancellation before it can store another turn.
            worker.cancel()

    return StreamingResponse(
        events(), media_type="application/x-ndjson",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )
