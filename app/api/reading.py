"""Track each paper's reading status independently of its indexed content."""
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Path
from psycopg.rows import dict_row
from pydantic import BaseModel, ConfigDict, Field

from app.db.connection import get_connection

router = APIRouter(prefix="/documents")


class ReadingUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page: int | None = Field(default=None, ge=1, le=100_000, strict=True)
    status: Literal["unread", "reading", "finished"] | None = None


@router.patch("/{document_id}/reading")
def update_reading(
    document_id: Annotated[int, Path(gt=0, le=9223372036854775807)],
    request: ReadingUpdate,
) -> dict:
    page, status = request.page, request.status
    if page is None and status is None:
        raise HTTPException(422, "Provide a reading status or page.")
    with get_connection() as conn, conn.cursor(row_factory=dict_row) as cursor:
        doc = cursor.execute("SELECT page_count FROM documents WHERE id=%s FOR UPDATE", (document_id,)).fetchone()
        if doc is None:
            raise HTTPException(404, "Document not found.")
        if page is not None:
            count = doc["page_count"]
            exists = page <= count if count is not None else cursor.execute("""
                SELECT EXISTS(
                    SELECT 1 FROM chunks WHERE document_id=%s AND page_start<=%s AND page_end>=%s
                ) AS indexed
            """, (document_id, page, page)).fetchone()["indexed"]
            if not exists:
                raise HTTPException(422, "Page is outside the available source.")
        return cursor.execute("""
            UPDATE documents SET
                reading_status=COALESCE(%s, CASE WHEN %s::int IS NOT NULL AND reading_status='unread'
                    THEN 'reading' ELSE reading_status END),
                last_read_page=COALESCE(%s,last_read_page),
                last_read_at=CASE WHEN %s::int IS NULL THEN last_read_at ELSE NOW() END
            WHERE id=%s RETURNING reading_status,last_read_page,last_read_at
        """, (status, page, page, page, document_id)).fetchone()
