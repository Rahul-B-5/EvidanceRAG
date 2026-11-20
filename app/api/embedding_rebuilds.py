"""API for polling and managing durable embedding rebuilds."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, HTTPException, Path
from pydantic import BaseModel

from app.retrieval.reembedding import cancel_rebuild, embedding_status, execute_rebuild, queue_rebuild

router = APIRouter(prefix="/documents/{document_id}", tags=["embeddings"])
DocumentID = Annotated[int, Path(gt=0, le=9223372036854775807)]


class EmbeddingRebuild(BaseModel):
    id: UUID
    document_id: int
    model: str
    dimensions: int
    total_chunks: int
    prepared_chunks: int
    status: Literal["queued", "running", "completed", "failed", "interrupted", "cancelled"]
    error: str | None
    created_at: datetime
    updated_at: datetime


class EmbeddingStatus(BaseModel):
    model: str
    dimensions: int
    active_chunks: int
    total_chunks: int
    job: EmbeddingRebuild | None


@router.get("/embeddings", response_model=EmbeddingStatus)
def read_embeddings(document_id: DocumentID) -> dict:
    result = embedding_status(document_id)
    if result is None:
        raise HTTPException(404, "Document not found.")
    return result


@router.post("/embeddings/rebuild", response_model=EmbeddingRebuild, status_code=202)
def start_rebuild(document_id: DocumentID, tasks: BackgroundTasks) -> dict:
    job, unavailable = queue_rebuild(document_id)
    if job is None:
        if unavailable == "missing":
            raise HTTPException(404, "Document not found.")
        if unavailable == "empty":
            raise HTTPException(422, "This paper has no indexed passages to re-embed.")
        raise HTTPException(409, "An embedding rebuild is already in progress for this paper.")
    tasks.add_task(execute_rebuild, job["id"])
    return job


@router.post("/embeddings/rebuild/{job_id}/cancel", status_code=204)
def stop_rebuild(document_id: DocumentID, job_id: UUID) -> None:
    if not cancel_rebuild(document_id, job_id):
        raise HTTPException(409, "This embedding rebuild is no longer active.")
