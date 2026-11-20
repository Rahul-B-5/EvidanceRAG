"""Save provenance and notes for passages independently of the active index."""
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path
from pydantic import BaseModel, Field, field_validator
from psycopg.rows import dict_row

from app.db.connection import get_connection

router = APIRouter(prefix="/saved-evidence")
ChunkId = Annotated[int, Path(gt=0, le=9223372036854775807)]


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


@router.get("")
def list_saved() -> dict:
    with get_connection() as conn, conn.cursor(row_factory=dict_row) as cursor:
        rows = cursor.execute("""
            SELECT s.*, EXISTS(SELECT 1 FROM documents d WHERE d.id = s.document_id) AS source_exists
            FROM saved_evidence s ORDER BY saved_at DESC, chunk_id DESC
        """).fetchall()
    return {"items": rows}


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
