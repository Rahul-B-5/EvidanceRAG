"""Local HTTP API for EvidenceRAG's document and evidence workflows."""

import uuid
from contextlib import suppress
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, Query, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from app.api.saved_evidence import router as saved_evidence_router

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
from research.comparison import compare_documents
from research.comparison_runs import cancel_run, create_run, execute_run, list_runs, run_details
from research.structured import structured_comparison
from research.atlas import atlas_for_workspace
from typing import Annotated


app = FastAPI(
    title="EvidenceRAG",
    version="0.1.0",
    description="A local-first, evidence-grounded research library API.",
)
app.include_router(saved_evidence_router)
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
    workspace_id: int | None = Field(default=None, gt=0)


class ConversationRequest(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    document_id: int | None = Field(default=None, gt=0)
    workspace_id: int | None = Field(default=None, gt=0)


class WorkspaceRequest(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=2_000)


class ComparisonRequest(BaseModel):
    document_ids: list[Annotated[int, Field(gt=0)]] = Field(min_length=2, max_length=12)
    passages_per_field: int = Field(default=2, ge=1, le=5)
    workspace_id: int | None = Field(default=None, gt=0)


class StructuredComparisonRequest(BaseModel):
    document_ids: list[Annotated[int, Field(gt=0, le=9223372036854775807)]] = Field(min_length=2, max_length=6)
    workspace_id: int | None = Field(default=None, gt=0, le=9223372036854775807)


def validate_workspace_scope(workspace_id: int | None, document_ids: list[int]) -> None:
    if workspace_id is None:
        return
    with get_connection() as conn:
        workspace = get_workspace(conn, workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found.")
    members = {d["id"] for d in workspace["documents"]}
    if set(document_ids) - members:
        raise HTTPException(status_code=422, detail="Selected documents are outside this workspace.")


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

    return FileResponse(path, media_type="application/pdf", filename=path.name, content_disposition_type="inline")


@app.get("/documents/{document_id}/passages")
def document_passages(
    document_id: Annotated[int, Field(gt=0)],
    page: int = Query(default=1, ge=1, le=100000),
) -> dict:
    with get_connection() as conn:
        if conn.execute("SELECT 1 FROM documents WHERE id = %s", (document_id,)).fetchone() is None:
            raise HTTPException(status_code=404, detail="Document not found.")
        rows = conn.execute(
            """SELECT id, page_start, page_end, text FROM chunks
               WHERE document_id = %s AND page_start <= %s AND page_end >= %s
               ORDER BY chunk_index LIMIT 25""",
            (document_id, page, page),
        ).fetchall()
    return {"passages": [
        {"chunk_id": r[0], "page_start": r[1], "page_end": r[2], "text": r[3]} for r in rows
    ]}


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
    workspace_id: int | None = Query(default=None, gt=0),
) -> dict:
    validate_workspace_scope(workspace_id, [document_id] if document_id is not None else [])
    try:
        return retrieve_evidence(query, top_k=top_k, document_id=document_id,
                                 **({"workspace_id": workspace_id} if workspace_id is not None else {}))
    except ValueError as exc:
        raise _bad_request(exc) from exc


@app.post("/answers")
def answer(request: AnswerRequest) -> dict:
    if not request.query.strip():
        raise HTTPException(status_code=422, detail="Query must not be empty.")
    document_id, workspace_id = request.document_id, request.workspace_id
    history = []
    try:
        if request.conversation_id is not None:
            with get_connection() as conn:
                conversation = get_conversation(conn, request.conversation_id)
                if conversation is None:
                    raise HTTPException(status_code=404, detail="Conversation not found.")
            for field in ("document_id", "workspace_id"):
                supplied = getattr(request, field)
                if supplied is not None and supplied != conversation.get(field):
                    raise HTTPException(status_code=409, detail="Conversation source scope cannot change.")
            document_id, workspace_id = conversation["document_id"], conversation.get("workspace_id")
            history = conversation["messages"]
            if document_id is not None:
                with get_connection() as conn:
                    if get_document(conn, document_id) is None:
                        raise HTTPException(status_code=404, detail="Conversation source was deleted.")
        validate_workspace_scope(workspace_id, [document_id] if document_id is not None else [])
        # Prior user questions resolve follow-ups; old assistant claims are not
        # evidence and old E-labels are never reused as current citations.
        prior_questions = [m["content"][:1000] for m in history if m["role"] == "user"][-3:]
        retrieval_query = "\n".join(prior_questions + [request.query])[-13000:]
        retrieval = retrieve_evidence(
            retrieval_query,
            top_k=request.top_k,
            document_id=document_id,
            workspace_id=workspace_id,
        )
        generated = generate_answer(
            request.query, retrieval["context"], retrieval["evidence"],
            **({"history": history[-6:]} if history else {}),
        )
    except ValueError as exc:
        raise _bad_request(exc) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    response = {**generated, "evidence": retrieval["evidence"]}
    if request.conversation_id is not None:
        assistant_content = generated["answer"] or generated["reason"] or "No answer generated."
        with get_connection() as conn:
            locked = conn.execute("SELECT id FROM conversations WHERE id = %s FOR UPDATE", (request.conversation_id,)).fetchone()
            if locked is None:
                raise HTTPException(status_code=404, detail="Conversation not found.")
            current_count = conn.execute("SELECT count(*) FROM messages WHERE conversation_id = %s", (request.conversation_id,)).fetchone()[0]
            if current_count != len(history):
                raise HTTPException(status_code=409, detail="Conversation changed; reload and retry.")
            add_message(conn, conversation_id=request.conversation_id, role="user", content=request.query)
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
    if not request.title.strip():
        raise HTTPException(status_code=422, detail="Title must not be empty.")
    validate_workspace_scope(request.workspace_id, [request.document_id] if request.document_id is not None else [])
    with get_connection() as conn:
        if request.document_id is not None and get_document(conn, request.document_id) is None:
            raise HTTPException(status_code=404, detail="Document not found.")
        return create_conversation(
            conn, title=request.title.strip(), document_id=request.document_id,
            workspace_id=request.workspace_id,
        )


@app.get("/conversations")
def conversations() -> dict:
    with get_connection() as conn:
        rows = conn.execute("SELECT id, title, updated_at FROM conversations ORDER BY updated_at DESC, id DESC LIMIT 100").fetchall()
    return {"conversations": [{"id": r[0], "title": r[1], "updated_at": r[2]} for r in rows]}


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
    if not request.name.strip():
        raise HTTPException(status_code=422, detail="Workspace name must not be empty.")
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


@app.post("/comparisons")
def comparison(request: ComparisonRequest) -> dict:
    titles = comparison_titles(request.document_ids, request.workspace_id)
    try:
        result = compare_documents(
            request.document_ids, passages_per_field=request.passages_per_field,
            workspace_id=request.workspace_id,
        )
        for paper in result["papers"]:
            paper["title"] = titles[paper["document_id"]]
        return result
    except ValueError as exc:
        raise _bad_request(exc) from exc


def comparison_titles(document_ids: list[int], workspace_id: int | None) -> dict[int, str]:
    validate_workspace_scope(workspace_id, document_ids)
    if len(set(document_ids)) != len(document_ids):
        raise HTTPException(status_code=422, detail="Select distinct documents.")
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, title FROM documents WHERE id = ANY(%s)",
            (document_ids,),
        ).fetchall()
    titles = dict(rows)
    if set(document_ids) - titles.keys():
        raise HTTPException(status_code=404, detail="One or more documents were not found.")
    return {id_: titles[id_] for id_ in document_ids}


@app.post("/comparisons/structured")
def compare_structured(request: StructuredComparisonRequest) -> dict:
    titles = comparison_titles(request.document_ids, request.workspace_id)
    try:
        return structured_comparison(titles, request.workspace_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/comparison-runs", status_code=202)
def start_comparison(request: StructuredComparisonRequest, tasks: BackgroundTasks) -> dict:
    titles = comparison_titles(request.document_ids, request.workspace_id)
    run = create_run(titles, request.workspace_id)
    if run is None:
        raise HTTPException(status_code=409, detail="A comparison is already running. Open it in run history or wait for it to finish.")
    tasks.add_task(execute_run, run["id"], titles, request.workspace_id)
    return run


@app.get("/comparison-runs")
def comparison_history(workspace_id: int | None = Query(default=None, gt=0)) -> dict:
    validate_workspace_scope(workspace_id, [])
    return {"runs": list_runs(workspace_id)}


@app.get("/comparison-runs/{run_id}")
def comparison_run(run_id: uuid.UUID) -> dict:
    run = run_details(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Comparison run not found.")
    validate_workspace_scope(run["workspace_id"], run["document_ids"])
    return run


@app.post("/comparison-runs/{run_id}/cancel", status_code=204)
def stop_comparison(run_id: uuid.UUID) -> None:
    comparison_run(run_id)
    if not cancel_run(run_id):
        raise HTTPException(status_code=409, detail="Comparison is no longer active.")


@app.get("/evidence-atlas")
def evidence_atlas(workspace_id: int | None = Query(default=None, gt=0, le=9223372036854775807)) -> dict:
    validate_workspace_scope(workspace_id, [])
    return atlas_for_workspace(workspace_id)


@app.delete("/workspaces/{workspace_id}/documents/{document_id}", status_code=204)
def detach_document(workspace_id: int, document_id: int) -> None:
    if workspace_id <= 0 or document_id <= 0:
        raise HTTPException(status_code=422, detail="IDs must be positive.")
    with get_connection() as conn:
        if get_workspace(conn, workspace_id) is None:
            raise HTTPException(status_code=404, detail="Workspace not found.")
        conn.execute(
            "DELETE FROM workspace_documents WHERE workspace_id = %s AND document_id = %s",
            (workspace_id, document_id),
        )
        conn.execute("UPDATE workspaces SET updated_at = NOW() WHERE id = %s", (workspace_id,))
