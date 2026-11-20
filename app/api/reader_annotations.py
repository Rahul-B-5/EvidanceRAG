"""Local library annotations anchored to source pages and indexed passages."""

from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Path, Query
from psycopg import Connection
from psycopg.rows import dict_row
from pydantic import BaseModel, Field, field_validator

from app.db.connection import get_connection

router = APIRouter(prefix="/documents/{document_id}", tags=["reader"])
DocumentID = Annotated[int, Path(gt=0, le=9223372036854775807)]
Page = Annotated[int, Field(ge=1, le=100_000)]
HIGHLIGHT_FIELDS = "id, chunk_id, page, start_offset, end_offset, quote, note, revision"


class HighlightNote(BaseModel):
    note: str = Field(max_length=4000)

    @field_validator("note")
    @classmethod
    def validate_note(cls, value: str) -> str:
        if "\x00" in value:
            raise ValueError("Notes cannot contain null characters.")
        return value


class NewHighlight(HighlightNote):
    page: Page
    chunk_id: int = Field(gt=0, le=9223372036854775807)
    start_offset: int = Field(ge=0, le=2147483647)
    end_offset: int = Field(gt=0, le=2147483647)


class EditHighlight(HighlightNote):
    revision: int = Field(gt=0, lt=2147483647)


class ReaderHighlight(EditHighlight):
    id: UUID
    chunk_id: int | None
    page: Page
    start_offset: int
    end_offset: int
    quote: str


class ReaderAnnotations(BaseModel):
    bookmarks: list[int]
    highlights: list[ReaderHighlight]


def require_document(conn: Connection, document_id: int) -> None:
    if conn.execute("SELECT id FROM documents WHERE id = %s FOR KEY SHARE", (document_id,)).fetchone() is None:
        raise HTTPException(404, "Document not found.")


@router.get("/reader-annotations", response_model=ReaderAnnotations)
def list_annotations(document_id: DocumentID, page: Annotated[int, Query(ge=1, le=100_000)]) -> dict:
    with get_connection() as conn:
        require_document(conn, document_id)
        bookmarks = conn.execute(
            "SELECT page FROM reader_bookmarks WHERE document_id = %s ORDER BY page", (document_id,)
        ).fetchall()
        highlights = conn.cursor(row_factory=dict_row).execute(
            f"""SELECT {HIGHLIGHT_FIELDS} FROM reader_highlights WHERE document_id = %s AND page = %s
                ORDER BY chunk_id NULLS LAST, start_offset, end_offset, id""",
            (document_id, page),
        ).fetchall()
    return {"bookmarks": [row[0] for row in bookmarks], "highlights": highlights}


@router.put("/reader-bookmarks/{page}", status_code=204)
def add_bookmark(document_id: DocumentID, page: Annotated[int, Path(ge=1, le=100_000)]) -> None:
    with get_connection() as conn:
        require_document(conn, document_id)
        maximum = conn.execute("""
            SELECT COALESCE(page_count, (SELECT MAX(page_end) FROM chunks WHERE document_id = documents.id), 0)
            FROM documents WHERE id = %s
        """, (document_id,)).fetchone()[0]
        if page > maximum:
            raise HTTPException(422, "Page is outside this document.")
        conn.execute(
            "INSERT INTO reader_bookmarks (document_id, page) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (document_id, page),
        )


@router.delete("/reader-bookmarks/{page}", status_code=204)
def remove_bookmark(document_id: DocumentID, page: Annotated[int, Path(ge=1, le=100_000)]) -> None:
    with get_connection() as conn:
        require_document(conn, document_id)
        conn.execute("DELETE FROM reader_bookmarks WHERE document_id = %s AND page = %s", (document_id, page))


@router.post("/reader-highlights", status_code=201, response_model=ReaderHighlight)
def create_highlight(document_id: DocumentID, request: NewHighlight) -> dict:
    with get_connection() as conn:
        require_document(conn, document_id)
        passage = conn.execute("""
            SELECT text FROM chunks WHERE id = %s AND document_id = %s AND %s BETWEEN page_start AND page_end
            FOR SHARE
        """, (request.chunk_id, document_id, request.page)).fetchone()
        if passage is None:
            raise HTTPException(404, "Passage not found on this page.")
        start, end = request.start_offset, request.end_offset
        if not 0 < end - start <= 2000 or end > len(passage[0]):
            raise HTTPException(422, "Select up to 2,000 characters within one indexed passage.")
        quote = passage[0][start:end]
        if not quote.strip():
            raise HTTPException(422, "Select text containing a visible character.")
        result = conn.cursor(row_factory=dict_row).execute(
            f"""INSERT INTO reader_highlights (id, document_id, page, chunk_id, start_offset, end_offset, quote, note)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (document_id, page, chunk_id, start_offset, end_offset) DO NOTHING
                RETURNING {HIGHLIGHT_FIELDS}""",
            (uuid4(), document_id, request.page, request.chunk_id, start, end, quote, request.note),
        ).fetchone()
        if result is None:
            raise HTTPException(409, "This selection already has a highlight.")
    return result


@router.patch("/reader-highlights/{highlight_id}", response_model=ReaderHighlight)
def edit_highlight(document_id: DocumentID, highlight_id: UUID, request: EditHighlight) -> dict:
    with get_connection() as conn:
        result = conn.cursor(row_factory=dict_row).execute(
            f"""UPDATE reader_highlights SET note = %s, revision = revision + 1
                WHERE document_id = %s AND id = %s AND revision = %s RETURNING {HIGHLIGHT_FIELDS}""",
            (request.note, document_id, highlight_id, request.revision),
        ).fetchone()
        if result is None:
            exists = conn.execute(
                "SELECT 1 FROM reader_highlights WHERE document_id = %s AND id = %s", (document_id, highlight_id),
            ).fetchone()
            if exists:
                raise HTTPException(409, "This note has changed. Reopen the page before editing.")
            raise HTTPException(404, "Highlight not found.")
    return result


@router.delete("/reader-highlights/{highlight_id}", status_code=204)
def remove_highlight(
    document_id: DocumentID, highlight_id: UUID, revision: Annotated[int, Query(gt=0, lt=2147483647)],
) -> None:
    with get_connection() as conn:
        deleted = conn.execute(
            "DELETE FROM reader_highlights WHERE document_id = %s AND id = %s AND revision = %s RETURNING id",
            (document_id, highlight_id, revision),
        ).fetchone()
        if not deleted and conn.execute(
            "SELECT 1 FROM reader_highlights WHERE document_id = %s AND id = %s", (document_id, highlight_id),
        ).fetchone():
            raise HTTPException(409, "This note has changed. Reopen the page before deleting.")
