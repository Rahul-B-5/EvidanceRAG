"""Local HTTP API for EvidenceRAG's document and evidence workflows."""

import uuid
import re
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, Query, UploadFile, status
from fastapi import Path as ApiPath
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from psycopg import Connection
from psycopg.errors import ForeignKeyViolation, UniqueViolation
from app.api.saved_evidence import router as saved_evidence_router
from app.api.reader_annotations import router as reader_annotations_router
from app.api.answer_stream import stream_answer

from app.core.config import get_settings
from app.db.connection import get_connection
from app.db import collections as library_collections
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
    update_document_metadata,
)
from app.generation.answerer import generate_answer
from app.generation.context_builder import build_evidence_context
from app.ingestion.pipeline import ingest_pdf
from app.retrieval.service import retrieve_evidence
from research.comparison import compare_documents
from research.comparison_runs import cancel_run, create_run, execute_run, list_runs, run_details
from research.structured import structured_comparison
from research.atlas import atlas_for_workspace
from research.counterevidence import find_candidates
from research.claim_reviews import read_reviews, write_review
from research.reproducibility import assess_document
from research.coverage import question_coverage
from research.gaps import research_directions
from research.packets import create_packet, edit_packet, list_packets, packet_detail
from typing import Annotated, Literal


app = FastAPI(
    title="EvidenceRAG",
    version="0.1.0",
    description="A local-first, evidence-grounded research library API.",
)
app.include_router(saved_evidence_router)
app.include_router(reader_annotations_router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in get_settings().cors_origins.split(",") if origin.strip()],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "Range"],
    expose_headers=["Accept-Ranges", "Content-Range"],
)

SourceID = Annotated[int, Field(gt=0, le=9223372036854775807)]
SourceSet = Annotated[list[SourceID], Field(min_length=1, max_length=12)]


class AnswerRequest(BaseModel):
    query: str = Field(min_length=1, max_length=10_000)
    document_id: SourceID | None = None
    document_ids: SourceSet | None = None
    top_k: int | None = Field(default=None, ge=1, le=50)
    conversation_id: int | None = Field(default=None, gt=0)
    workspace_id: int | None = Field(default=None, gt=0)


class ConversationRequest(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    document_id: SourceID | None = None
    document_ids: SourceSet | None = None
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


class ClaimReviewRequest(BaseModel):
    relation: Literal["supports", "qualifies", "challenges", "uncertain"]
    alignment: Literal["aligned", "different", "unknown"]
    note: str = Field(default="", max_length=4000)


class CoverageRequest(BaseModel):
    question: str = Field(min_length=8, max_length=1200)
    workspace_id: int | None = Field(default=None, gt=0, le=9223372036854775807)
    use_provider: bool = False


class PacketRequest(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    question: str = Field(default="", max_length=1500)
    workspace_id: int | None = Field(default=None, gt=0, le=9223372036854775807)
    chunk_ids: list[Annotated[int, Field(gt=0, le=9223372036854775807)]] = Field(min_length=1, max_length=50)


class PacketEdit(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    question: str = Field(default="", max_length=1500)
    narrative: str = Field(default="", max_length=30000)
    revision: int = Field(gt=0, le=2147483646)


class DocumentMetadata(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    authors: list[Annotated[str, Field(max_length=200)]] = Field(default_factory=list, max_length=100)
    publication_year: int | None = Field(default=None, ge=1000, le=3000)
    doi: str | None = Field(default=None, max_length=220)
    venue: str | None = Field(default=None, max_length=200)
    tags: list[Annotated[str, Field(max_length=48)]] = Field(default_factory=list, max_length=30)
    metadata_revision: int = Field(gt=0, le=2147483646)


class CollectionName(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class CollectionRequest(CollectionName):
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


def requested_source_set(document_id: int | None, document_ids: list[int] | None) -> list[int]:
    if document_ids is None:
        return [document_id] if document_id is not None else []
    if document_id is not None:
        raise HTTPException(422, "Provide either document_id or document_ids.")
    if len(set(document_ids)) != len(document_ids):
        raise HTTPException(422, "Selected documents must be distinct.")
    return document_ids


def require_selected_papers(conn: Connection, document_ids: list[int], workspace_id: int | None = None) -> None:
    if workspace_id is None:
        found = conn.execute(
            "SELECT id FROM documents WHERE id = ANY(%s::bigint[]) FOR KEY SHARE", (document_ids,),
        ).fetchall()
    else:
        found = conn.execute("""
            SELECT document_id FROM workspace_documents
            WHERE workspace_id = %s AND document_id = ANY(%s::bigint[]) FOR KEY SHARE
        """, (workspace_id, document_ids)).fetchall()
    if len(found) != len(document_ids):
        if workspace_id is not None:
            raise HTTPException(422, "Selected documents are outside this workspace.")
        raise HTTPException(404, "A selected paper is no longer in the library.")


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


@app.patch("/documents/{document_id}/metadata")
def edit_document_metadata(
    document_id: Annotated[int, ApiPath(gt=0, le=9223372036854775807)],
    request: DocumentMetadata,
) -> dict:
    title = request.title.strip()
    if not title:
        raise HTTPException(status_code=422, detail="Document title cannot be empty.")
    doi = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", (request.doi or "").strip(), flags=re.IGNORECASE)
    if doi and not re.fullmatch(r"10\.\d{4,9}/[^\s\x00-\x1f\x7f]+", doi, flags=re.IGNORECASE):
        raise HTTPException(status_code=422, detail="Use a DOI in the form 10.xxxx/suffix or a doi.org URL.")
    authors = list(dict.fromkeys(v.strip() for v in request.authors if v.strip()))
    tags = list({v.strip().casefold(): v.strip() for v in request.tags if v.strip()}.values())
    with get_connection() as conn:
        result = update_document_metadata(
            conn, document_id, request.metadata_revision,
            title=title, authors=authors, publication_year=request.publication_year,
            doi=doi or None, venue=(request.venue or "").strip() or None, tags=tags,
        )
        if result is None:
            if get_document(conn, document_id) is None:
                raise HTTPException(status_code=404, detail="Document not found.")
            raise HTTPException(status_code=409, detail="Metadata changed in another tab. Refresh the library before saving.")
    return result


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
    document_id: SourceID | None = Query(default=None),
    document_ids: Annotated[list[SourceID] | None, Query(min_length=1, max_length=12)] = None,
    top_k: int | None = Query(default=None, ge=1, le=50),
    workspace_id: int | None = Query(default=None, gt=0),
) -> dict:
    selected = requested_source_set(document_id, document_ids)
    validate_workspace_scope(workspace_id, selected)
    try:
        return retrieve_evidence(query, top_k=top_k, document_id=document_id,
                                 **({"workspace_id": workspace_id} if workspace_id is not None else {}),
                                 **({"document_ids": document_ids} if document_ids is not None else {}))
    except ValueError as exc:
        raise _bad_request(exc) from exc


@app.post("/answers")
def answer(request: AnswerRequest) -> dict:
    return answer_exchange(request)


@app.post("/answers/stream", response_class=StreamingResponse)
async def answer_stream(request: AnswerRequest) -> StreamingResponse:
    return stream_answer(lambda progress: answer_exchange(request, progress))


def answer_exchange(request: AnswerRequest, progress: Callable[[str], None] = lambda _: None) -> dict:
    if not request.query.strip():
        raise HTTPException(status_code=422, detail="Query must not be empty.")
    document_id, workspace_id = request.document_id, request.workspace_id
    document_ids = request.document_ids
    requested_source_set(document_id, document_ids)
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
            persisted_ids = conversation.get("document_ids")
            if document_ids is not None and set(document_ids) != set(persisted_ids or []):
                raise HTTPException(409, "Conversation source scope cannot change.")
            document_id, workspace_id = conversation["document_id"], conversation.get("workspace_id")
            document_ids = persisted_ids
            history = conversation["messages"]
            if document_id is not None:
                with get_connection() as conn:
                    if get_document(conn, document_id) is None:
                        raise HTTPException(status_code=404, detail="Conversation source was deleted.")
        selected = requested_source_set(document_id, document_ids)
        retrieved = set()
        validate_workspace_scope(workspace_id, selected)
        if document_ids is not None:
            with get_connection() as conn:
                require_selected_papers(conn, document_ids)
        # Prior user questions resolve follow-ups; old assistant claims are not
        # evidence and old E-labels are never reused as current citations.
        progress("retrieving")
        prior_questions = [m["content"][:1000] for m in history if m["role"] == "user"][-3:]
        retrieval_query = "\n".join(prior_questions + [request.query])[-13000:]
        retrieval = retrieve_evidence(
            retrieval_query,
            top_k=request.top_k,
            document_id=document_id,
            workspace_id=workspace_id,
            **({"document_ids": document_ids} if document_ids is not None else {}),
        )
        if workspace_id is not None:
            retrieved = {item["document_id"] for item in retrieval["evidence"]}
            validate_workspace_scope(workspace_id, list(retrieved.union(selected)))
        # User turns can resolve follow-ups, while historic workspace answers
        # may reference papers that have since been detached.
        provider_history = [m for m in history if m["role"] == "user"] if workspace_id else history
        progress("generating")
        generated = generate_answer(
            request.query, retrieval["context"], retrieval["evidence"],
            **({"history": provider_history[-6:]} if provider_history else {}),
        )
    except ValueError as exc:
        raise _bad_request(exc) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    response = {**generated, "evidence": retrieval["evidence"]}
    progress("")
    if request.conversation_id is not None:
        progress("saving")
        assistant_content = generated["answer"] or generated["reason"] or "No answer generated."
        with get_connection() as conn:
            if workspace_id is not None and (retrieved or selected):
                require_selected_papers(conn, sorted(retrieved.union(selected)), workspace_id)
            elif document_ids is not None:
                require_selected_papers(conn, document_ids)
            locked = conn.execute("SELECT id FROM conversations WHERE id = %s FOR UPDATE", (request.conversation_id,)).fetchone()
            if locked is None:
                raise HTTPException(status_code=404, detail="Conversation not found.")
            current_count = conn.execute("SELECT count(*) FROM messages WHERE conversation_id = %s", (request.conversation_id,)).fetchone()[0]
            if current_count != len(history):
                raise HTTPException(status_code=409, detail="Conversation changed; reload and retry.")
            progress("")
            add_message(conn, conversation_id=request.conversation_id, role="user", content=request.query)
            add_message(
                conn,
                conversation_id=request.conversation_id,
                role="assistant",
                content=assistant_content,
                citations=generated["citations"],
            )
            progress("")
    return response


@app.post("/conversations", status_code=status.HTTP_201_CREATED)
def new_conversation(request: ConversationRequest) -> dict:
    if not request.title.strip():
        raise HTTPException(status_code=422, detail="Title must not be empty.")
    selected = requested_source_set(request.document_id, request.document_ids)
    validate_workspace_scope(request.workspace_id, selected)
    with get_connection() as conn:
        if request.document_id is not None and get_document(conn, request.document_id) is None:
            raise HTTPException(status_code=404, detail="Document not found.")
        if request.document_ids is not None:
            require_selected_papers(conn, request.document_ids, request.workspace_id)
        return create_conversation(
            conn, title=request.title.strip(), document_id=request.document_id,
            workspace_id=request.workspace_id,
            document_ids=request.document_ids,
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


@app.get("/evidence-atlas/{finding_id}/counterevidence")
def finding_counterevidence(
    finding_id: Annotated[str, ApiPath(pattern=r"^finding:[0-9a-f]{24}$")],
    workspace_id: int | None = Query(default=None, gt=0, le=9223372036854775807),
) -> dict:
    finding, contradictions = resolve_finding(finding_id, workspace_id)
    return {"finding": finding, "passages": find_candidates(finding, workspace_id, contradictions),
            "reviews": read_reviews(finding_id, workspace_id)}


def resolve_finding(finding_id: str, workspace_id: int | None) -> tuple[dict, list[dict]]:
    validate_workspace_scope(workspace_id, [])
    atlas = atlas_for_workspace(workspace_id)
    finding = next((node for node in atlas["nodes"]
                    if node["kind"] == "finding" and node["id"] == finding_id), None)
    if finding is None:
        raise HTTPException(status_code=404, detail="Finding not found in this scope.")
    return finding, atlas["contradictions"]


@app.put("/evidence-atlas/{finding_id}/reviews/{chunk_id}")
def save_claim_review(
    finding_id: Annotated[str, ApiPath(pattern=r"^finding:[0-9a-f]{24}$")],
    chunk_id: Annotated[int, ApiPath(gt=0, le=9223372036854775807)],
    request: ClaimReviewRequest,
    workspace_id: int | None = Query(default=None, gt=0, le=9223372036854775807),
) -> dict:
    finding, contradictions = resolve_finding(finding_id, workspace_id)
    matches = find_candidates(finding, workspace_id, contradictions)
    candidate = next((p for p in matches if p["chunk_id"] == chunk_id), None)
    if candidate is None:
        saved = next((item for item in read_reviews(finding_id, workspace_id)
                      if item["candidate_chunk_id"] == chunk_id), None)
        if saved is None:
            raise HTTPException(status_code=404, detail="Candidate passage not found in this scope.")
        candidate = saved["candidate_snapshot"]
    review = write_review(finding, candidate, workspace_id, request.relation, request.alignment, request.note)
    if review is None:
        raise HTTPException(status_code=409, detail="Workspace membership changed. Reload before reviewing.")
    return review


@app.get("/documents/{document_id}/reproducibility")
def reproducibility_dossier(
    document_id: Annotated[int, ApiPath(gt=0, le=9223372036854775807)],
    workspace_id: int | None = Query(default=None, gt=0, le=9223372036854775807),
) -> dict:
    validate_workspace_scope(workspace_id, [document_id])
    with get_connection() as conn:
        row = conn.execute("SELECT title FROM documents WHERE id=%s", (document_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    return {"document_id": document_id, "title": row[0], "items": assess_document(document_id, workspace_id)}


@app.post("/research/coverage")
def map_coverage(request: CoverageRequest) -> dict:
    validate_workspace_scope(request.workspace_id, [])
    try:
        return question_coverage(request.question.strip(), request.workspace_id, request.use_provider)
    except ValueError as exc:
        raise _bad_request(exc) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/research/directions")
def explore_directions(
    workspace_id: int | None = Query(default=None, gt=0, le=9223372036854775807),
    focus: str = Query(default="", max_length=180),
) -> dict:
    validate_workspace_scope(workspace_id, [])
    return research_directions(workspace_id, focus.strip())


@app.post("/evidence-packets", status_code=201)
def new_packet(request: PacketRequest) -> dict:
    title = request.title.strip()
    if not title or len(set(request.chunk_ids)) != len(request.chunk_ids):
        raise HTTPException(status_code=422, detail="Supply a title and select distinct saved passages.")
    validate_workspace_scope(request.workspace_id, [])
    packet = create_packet(request.workspace_id, title, request.question.strip(), request.chunk_ids)
    if packet is None:
        raise HTTPException(status_code=422, detail="At least one saved passage is missing or outside this workspace.")
    return packet


@app.get("/evidence-packets")
def evidence_packets(workspace_id: int | None = Query(default=None, gt=0, le=9223372036854775807)) -> dict:
    validate_workspace_scope(workspace_id, [])
    return {"packets": list_packets(workspace_id)}


@app.get("/evidence-packets/{packet_id}")
def get_packet(packet_id: uuid.UUID) -> dict:
    packet = packet_detail(packet_id)
    if packet is None:
        raise HTTPException(status_code=404, detail="Evidence packet not found in its current scope.")
    return packet


@app.patch("/evidence-packets/{packet_id}")
def update_packet(packet_id: uuid.UUID, request: PacketEdit) -> dict:
    title = request.title.strip()
    if not title:
        raise HTTPException(status_code=422, detail="Supply a packet title.")
    packet = edit_packet(packet_id, request.revision, title, request.question.strip(), request.narrative)
    if packet is None:
        get_packet(packet_id)
        raise HTTPException(status_code=409, detail="The packet has changed. Reopen it before saving.")
    return packet


@app.post("/evidence-packets/{packet_id}/draft")
def draft_packet(packet_id: uuid.UUID) -> dict:
    packet = get_packet(packet_id)
    # One bounded source context for a review draft. The exported E-labels
    # continue to refer to the immutable packet item order.
    if len(packet["items"]) > 16:
        raise HTTPException(status_code=422, detail="Drafting supports up to 16 packet passages. Export is available for larger packets.")
    passages = [{**item, "text": item["passage"]} for item in packet["items"]]
    context, evidence = build_evidence_context(passages, max_chars_per_chunk=1150)
    query = (
        "Draft a concise research briefing with sections for findings, limitations, "
        "and unresolved questions. Cite each substantive observation. "
        f"Research question: {packet['question'] or packet['title']}"
    )
    try:
        return generate_answer(query, context, evidence)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


CollectionID = Annotated[int, ApiPath(gt=0, le=9223372036854775807)]


def checked_collection_name(name: str) -> str:
    if not (name := name.strip()):
        raise HTTPException(status_code=422, detail="Supply a collection name.")
    return name


@app.get("/collections")
def collections(workspace_id: int | None = Query(default=None, gt=0, le=9223372036854775807)) -> dict:
    validate_workspace_scope(workspace_id, [])
    return {"collections": library_collections.collection_list(workspace_id)}


@app.post("/collections", status_code=201)
def new_collection(request: CollectionRequest) -> dict:
    validate_workspace_scope(request.workspace_id, [])
    try:
        return library_collections.create_collection(request.workspace_id, checked_collection_name(request.name))
    except UniqueViolation:
        raise HTTPException(status_code=409, detail="A collection with this name already exists in the scope.") from None
    except ForeignKeyViolation:
        raise HTTPException(status_code=404, detail="Workspace not found.") from None


@app.get("/collections/{collection_id}")
def get_collection(collection_id: CollectionID) -> dict:
    result = library_collections.collection_detail(collection_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Collection not found.")
    return result


@app.patch("/collections/{collection_id}")
def update_collection(collection_id: CollectionID, request: CollectionName) -> dict:
    try:
        if not library_collections.rename_collection(collection_id, checked_collection_name(request.name)):
            raise HTTPException(status_code=404, detail="Collection not found.")
    except UniqueViolation:
        raise HTTPException(status_code=409, detail="A collection with this name already exists in the scope.") from None
    return get_collection(collection_id)


def set_collection_membership(collection_id: int, document_id: int, attach: bool) -> None:
    result = library_collections.change_collection_membership(collection_id, document_id, attach)
    if result == "missing_collection":
        raise HTTPException(status_code=404, detail="Collection not found.")
    if result == "missing_document":
        raise HTTPException(status_code=404, detail="Document not found.")
    if result == "outside_workspace":
        raise HTTPException(status_code=422, detail="The paper must be in the collection's workspace.")


@app.put("/collections/{collection_id}/documents/{document_id}", status_code=204)
def attach_collection_paper(collection_id: CollectionID, document_id: CollectionID) -> None:
    set_collection_membership(collection_id, document_id, True)


@app.delete("/collections/{collection_id}/documents/{document_id}", status_code=204)
def detach_collection_paper(collection_id: CollectionID, document_id: CollectionID) -> None:
    set_collection_membership(collection_id, document_id, False)


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
