"""Local HTTP API for EvidenceRAG's document and evidence workflows."""

import uuid
from contextlib import suppress
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Query, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.db.connection import get_connection
from app.db.repository import (
    add_message,
    create_conversation,
    delete_document,
    get_conversation,
    get_document,
    get_document_source_path,
    list_documents,
    add_document_to_workspace,
    create_workspace,
    get_workspace,
    list_workspaces,
)
from app.generation.answerer import generate_answer
from app.ingestion.pipeline import ingest_pdf
from app.retrieval.service import retrieve_evidence


app = FastAPI(
    title="EvidenceRAG",
    version="0.1.0",
    description="A local-first, evidence-grounded research library API.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in get_settings().cors_origins.split(",") if origin.strip()],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Content-Type"],
)


class AnswerRequest(BaseModel):
    query: str = Field(min_length=1, max_length=10_000)
    document_id: int | None = Field(default=None, gt=0)
    top_k: int | None = Field(default=None, ge=1, le=50)
    conversation_id: int | None = Field(default=None, gt=0)


class ConversationRequest(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    document_id: int | None = Field(default=None, gt=0)


class WorkspaceRequest(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=2_000)


def _bad_request(error: ValueError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error))


@app.get("/health")
def health() -> dict:
    """Verify the configured database is reachable without revealing credentials."""
    try:
        with get_connection() as conn:
            conn.execute("SELECT 1").fetchone()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is unavailable.",
        ) from exc
    return {"status": "ok"}


@app.get("/documents")
def documents() -> dict:
    with get_connection() as conn:
        return {"documents": list_documents(conn)}


@app.get("/documents/{document_id}")
def document_detail(document_id: int) -> dict:
    if document_id <= 0:
        raise HTTPException(status_code=422, detail="document_id must be positive.")
    with get_connection() as conn:
        document = get_document(conn, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    return document


def _delete_managed_source(stored_path: str | None) -> None:
    if not stored_path:
        return
    path = Path(stored_path)
    try:
        path.resolve().relative_to(get_settings().upload_dir.resolve())
    except ValueError:
        return
    with suppress(FileNotFoundError):
        path.unlink()


@app.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_document(document_id: int) -> None:
    if document_id <= 0:
        raise HTTPException(status_code=422, detail="document_id must be positive.")
    with get_connection() as conn:
        found, stored_path = delete_document(conn, document_id)
    if not found:
        raise HTTPException(status_code=404, detail="Document not found.")
    # The database commit happens before the source is unlinked. A missing
    # source is harmless; a source outside managed storage is never touched.
    _delete_managed_source(stored_path)


@app.get("/documents/{document_id}/source")
def document_source(document_id: int) -> FileResponse:
    if document_id <= 0:
        raise HTTPException(status_code=422, detail="document_id must be positive.")

    with get_connection() as conn:
        stored_path = get_document_source_path(conn, document_id)

    if not stored_path:
        raise HTTPException(status_code=404, detail="Original source is not available.")

    path = Path(stored_path)
    try:
        path.resolve().relative_to(get_settings().upload_dir.resolve())
    except ValueError:
        # A database value must never turn this local-only endpoint into an
        # arbitrary-file reader.
        raise HTTPException(status_code=404, detail="Original source file is missing.")

    if not path.is_file():
        raise HTTPException(status_code=404, detail="Original source file is missing.")

    return FileResponse(path, media_type="application/pdf", filename=path.name)


@app.post("/documents", status_code=status.HTTP_201_CREATED)
def upload_document(file: UploadFile = File(...)) -> dict:
    """Accept one PDF, stage it locally, then ingest it transactionally."""
    if not file.filename or Path(file.filename).suffix.lower() != ".pdf":
        raise HTTPException(status_code=422, detail="Only PDF files are supported.")

    settings = get_settings()
    staging_dir = settings.upload_dir / ".staging"
    request_dir = staging_dir / uuid.uuid4().hex
    request_dir.mkdir(parents=True, exist_ok=False)
    # `Path.name` removes any path supplied by a client while retaining the
    # original filename for metadata fallbacks and library display.
    staged_path = request_dir / Path(file.filename).name
    max_bytes = settings.max_upload_mb * 1024 * 1024

    try:
        written = 0
        with staged_path.open("wb") as output:
            while block := file.file.read(1024 * 1024):
                written += len(block)
                if written > max_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=f"PDF exceeds the configured {settings.max_upload_mb} MB limit.",
                    )
                output.write(block)

        try:
            result = ingest_pdf(staged_path)
            if result["status"] == "already_exists":
                return JSONResponse(status_code=status.HTTP_200_OK, content=result)
            return result
        except ValueError as exc:
            raise _bad_request(exc) from exc
    finally:
        file.file.close()
        with suppress(FileNotFoundError):
            staged_path.unlink()
        with suppress(OSError):
            request_dir.rmdir()


@app.get("/search")
def search(
    query: str = Query(min_length=1, max_length=10_000),
    document_id: int | None = Query(default=None, gt=0),
    top_k: int | None = Query(default=None, ge=1, le=50),
) -> dict:
    try:
        return retrieve_evidence(query, top_k=top_k, document_id=document_id)
    except ValueError as exc:
        raise _bad_request(exc) from exc


@app.post("/answers")
def answer(request: AnswerRequest) -> dict:
    try:
        if request.conversation_id is not None:
            with get_connection() as conn:
                if get_conversation(conn, request.conversation_id) is None:
                    raise HTTPException(status_code=404, detail="Conversation not found.")
                add_message(
                    conn,
                    conversation_id=request.conversation_id,
                    role="user",
                    content=request.query,
                )
        retrieval = retrieve_evidence(
            request.query,
            top_k=request.top_k,
            document_id=request.document_id,
        )
        generated = generate_answer(
            request.query, retrieval["context"], retrieval["evidence"]
        )
    except ValueError as exc:
        raise _bad_request(exc) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    response = {**generated, "evidence": retrieval["evidence"]}
    if request.conversation_id is not None:
        assistant_content = generated["answer"] or generated["reason"] or "No answer generated."
        with get_connection() as conn:
            add_message(
                conn,
                conversation_id=request.conversation_id,
                role="assistant",
                content=assistant_content,
                citations=generated["citations"],
            )
    return response


@app.post("/conversations", status_code=status.HTTP_201_CREATED)
def new_conversation(request: ConversationRequest) -> dict:
    with get_connection() as conn:
        if request.document_id is not None and get_document(conn, request.document_id) is None:
            raise HTTPException(status_code=404, detail="Document not found.")
        return create_conversation(
            conn, title=request.title.strip(), document_id=request.document_id
        )


@app.get("/conversations/{conversation_id}")
def conversation_detail(conversation_id: int) -> dict:
    if conversation_id <= 0:
        raise HTTPException(status_code=422, detail="conversation_id must be positive.")
    with get_connection() as conn:
        conversation = get_conversation(conn, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return conversation


@app.get("/workspaces")
def workspaces() -> dict:
    with get_connection() as conn:
        return {"workspaces": list_workspaces(conn)}


@app.post("/workspaces", status_code=status.HTTP_201_CREATED)
def new_workspace(request: WorkspaceRequest) -> dict:
    with get_connection() as conn:
        return create_workspace(
            conn, name=request.name.strip(),
            description=request.description.strip() if request.description else None,
        )


@app.get("/workspaces/{workspace_id}")
def workspace_detail(workspace_id: int) -> dict:
    if workspace_id <= 0:
        raise HTTPException(status_code=422, detail="workspace_id must be positive.")
    with get_connection() as conn:
        workspace = get_workspace(conn, workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found.")
    return workspace


@app.put("/workspaces/{workspace_id}/documents/{document_id}", status_code=status.HTTP_201_CREATED)
def attach_document_to_workspace(workspace_id: int, document_id: int) -> dict:
    if workspace_id <= 0 or document_id <= 0:
        raise HTTPException(status_code=422, detail="Workspace and document IDs must be positive.")
    with get_connection() as conn:
        if get_workspace(conn, workspace_id) is None:
            raise HTTPException(status_code=404, detail="Workspace not found.")
        if get_document(conn, document_id) is None:
            raise HTTPException(status_code=404, detail="Document not found.")
        added = add_document_to_workspace(
            conn, workspace_id=workspace_id, document_id=document_id
        )
    return {"workspace_id": workspace_id, "document_id": document_id, "added": added}
