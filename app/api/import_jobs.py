"""HTTP routes and worker lifecycle for durable PDF imports."""

import asyncio
import logging
from contextlib import asynccontextmanager, suppress
from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel

from app.ingestion.jobs import UploadTooLarge, enqueue, list_jobs, process_next_job, retry_job

router = APIRouter(prefix="/import-jobs", tags=["imports"])
logger = logging.getLogger(__name__)


class ImportJob(BaseModel):
    id: UUID
    filename: str
    state: Literal["queued", "indexing", "imported", "duplicate", "failed"]
    document_id: int | None
    error: str | None
    retryable: bool
    attempts: int
    created_at: datetime
    updated_at: datetime


class ImportJobs(BaseModel):
    jobs: list[ImportJob]


async def drain_imports() -> None:
    while True:
        try:
            if await asyncio.to_thread(process_next_job):
                continue
            await asyncio.sleep(0.65)
        except Exception as exc:
            logger.warning("Import queue unavailable (%s).", type(exc).__name__)
            await asyncio.sleep(5)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    worker = asyncio.create_task(drain_imports())
    try:
        yield
    finally:
        worker.cancel()
        with suppress(asyncio.CancelledError):
            await worker


@router.get("", response_model=ImportJobs)
def imports() -> dict:
    return {"jobs": list_jobs()}


@router.post("", status_code=202, response_model=ImportJob)
def upload_job(file: UploadFile = File(...)) -> dict:
    try:
        return enqueue(file)
    except UploadTooLarge as exc:
        raise HTTPException(413, str(exc)) from None
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    except OSError:
        raise HTTPException(503, "Unable to stage the PDF. Check the upload directory.") from None


@router.post("/{job_id}/retry", status_code=202, response_model=ImportJob)
def retry(job_id: UUID) -> dict:
    job = retry_job(job_id)
    if job is None:
        raise HTTPException(409, "This import cannot be retried. Upload the source again if needed.")
    return job
