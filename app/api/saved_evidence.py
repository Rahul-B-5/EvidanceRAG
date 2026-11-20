"""Save provenance and notes for passages independently of the active index."""
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query
from pydantic import BaseModel, Field, field_validator
from psycopg.rows import dict_row

from app.db.connection import get_connection

router = APIRouter(prefix="/saved-evidence")
ChunkId = Annotated[int, Path(gt=0, le=9223372036854775807)]
ScopeId = Annotated[int | None, Query(gt=0, le=9223372036854775807)]
SCOPE_FILTER = """
    (%(workspace)s::bigint IS NULL OR EXISTS (
        SELECT 1 FROM workspace_documents w WHERE w.workspace_id=%(workspace)s AND w.document_id=entry.document_id
    ))
    AND (%(collection)s::bigint IS NULL OR EXISTS (
        SELECT 1 FROM collection_documents c WHERE c.collection_id=%(collection)s AND c.document_id=entry.document_id
    ))
"""


class Note(BaseModel):
    note: str = Field(max_length=20_000)


class PassageTags(BaseModel):
    tags: list[Annotated[str, Field(max_length=80)]] = Field(max_length=12)

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, tags: list[str]) -> list[str]:
        normalized = [" ".join(tag.split()).casefold() for tag in tags]
        if any(not tag or "," in tag or len(tag) > 80 or not tag.isprintable() for tag in normalized):
            raise ValueError("Each tag must have 1–80 printable characters and contain no commas.")
        return list(dict.fromkeys(normalized))


def notebook_scope(cursor, workspace_id: int | None, collection_id: int | None) -> dict:
    if workspace_id is not None and cursor.execute("SELECT id FROM workspaces WHERE id=%s", (workspace_id,)).fetchone() is None:
        raise HTTPException(404, "Workspace not found.")
    if collection_id is not None and cursor.execute("""
        SELECT id FROM collections WHERE id=%s AND workspace_id IS NOT DISTINCT FROM %s::bigint
    """, (collection_id, workspace_id)).fetchone() is None:
        raise HTTPException(404, "Collection not found in this scope.")
    return {"workspace": workspace_id, "collection": collection_id}


@router.get("")
def list_saved(workspace_id: ScopeId = None, collection_id: ScopeId = None) -> dict:
    with get_connection() as conn, conn.cursor(row_factory=dict_row) as cursor:
        scope = notebook_scope(cursor, workspace_id, collection_id)
        rows = cursor.execute(f"""
            SELECT entry.*, EXISTS(SELECT 1 FROM documents d WHERE d.id = entry.document_id) AS source_exists
            FROM saved_evidence entry WHERE {SCOPE_FILTER}
            ORDER BY saved_at DESC, chunk_id DESC
        """, scope).fetchall()
    return {"items": rows}


@router.get("/highlights")
def list_highlights(
    workspace_id: ScopeId = None, collection_id: ScopeId = None,
    query: str = Query(default="", max_length=180),
    offset: int = Query(default=0, ge=0, le=10_000), limit: int = Query(default=40, ge=1, le=100),
) -> dict:
    with get_connection() as conn, conn.cursor(row_factory=dict_row) as cursor:
        scope = notebook_scope(cursor, workspace_id, collection_id)
        rows = cursor.execute(f"""
            SELECT entry.id, entry.document_id, d.title, entry.page, entry.quote, entry.note,
                   COALESCE(entry.page BETWEEN c.page_start AND c.page_end AND
                       substring(c.text from entry.start_offset + 1 for char_length(entry.quote)) = entry.quote,
                       FALSE) AS anchor_current
            FROM reader_highlights entry JOIN documents d ON d.id=entry.document_id
            LEFT JOIN chunks c ON c.id=entry.chunk_id AND c.document_id=d.id
            WHERE {SCOPE_FILTER}
              AND NOT EXISTS (
                  SELECT 1 FROM unnest(%(terms)s::text[]) AS term
                  WHERE strpos(lower(concat_ws(' ',d.title, entry.quote, entry.note)), lower(term))=0
              )
            ORDER BY lower(d.title), entry.document_id, entry.page, entry.start_offset, entry.id
            OFFSET %(offset)s LIMIT %(limit)s
        """, {**scope, "terms": query.split(), "limit": limit+1, "offset": offset}).fetchall()
    return {"items": rows[:limit], "has_more": len(rows) > limit}


@router.put("/{chunk_id}")
def save_passage(chunk_id: ChunkId) -> dict:
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO saved_evidence (chunk_id, document_id, title, page_start, page_end, passage)
            SELECT c.id, d.id, d.title, c.page_start, c.page_end, c.text
            FROM chunks c JOIN documents d ON d.id = c.document_id WHERE c.id = %s
            ON CONFLICT (chunk_id) DO NOTHING
        """, (chunk_id,))
        if conn.execute("SELECT 1 FROM saved_evidence WHERE chunk_id = %s", (chunk_id,)).fetchone() is None:
            raise HTTPException(404, "Passage not found.")
    return {"chunk_id": chunk_id}


@router.patch("/{chunk_id}")
def update_note(chunk_id: ChunkId, request: Note) -> dict:
    with get_connection() as conn:
        row = conn.execute(
            "UPDATE saved_evidence SET note = %s WHERE chunk_id = %s RETURNING note",
            (request.note, chunk_id),
        ).fetchone()
        if row is None:
            raise HTTPException(404, "Saved passage not found.")
    return {"chunk_id": chunk_id, "note": row[0]}


@router.put("/{chunk_id}/tags")
def update_tags(chunk_id: ChunkId, request: PassageTags) -> dict:
    with get_connection() as conn:
        row = conn.execute(
            "UPDATE saved_evidence SET tags = %s WHERE chunk_id = %s RETURNING tags",
            (request.tags, chunk_id),
        ).fetchone()
        if row is None:
            raise HTTPException(404, "Saved passage not found.")
    return {"chunk_id": chunk_id, "tags": row[0]}
