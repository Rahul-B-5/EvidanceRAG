
import re

from app.core.config import get_settings
from app.db.connection import get_connection

EXPLICIT_SEARCH = re.compile(r'"|(?:^|\s)-\w|\bOR\b', re.IGNORECASE)


def search_keyword(
    query: str,
    top_k: int | None = None,
    document_id: int | None = None,
    workspace_id: int | None = None,
    document_ids: list[int] | None = None,
    *,
    allow_partial: bool = False,
) -> list[dict]:
    """
    Retrieve relevant chunks using PostgreSQL full-text search.

    PostgreSQL tokenizes and normalizes text, then ranks matching
    passages using ts_rank_cd.
    """
    if not query.strip():
        raise ValueError("Search query must not be empty.")

    settings = get_settings()
    limit = top_k if top_k is not None else settings.retrieval_top_k

    if limit <= 0:
        raise ValueError("top_k must be positive.")

    if document_id is not None and document_id <= 0:
        raise ValueError("document_id must be positive.")
    if workspace_id is not None and workspace_id <= 0:
        raise ValueError("workspace_id must be positive.")

    sql = """
        SELECT
            c.id AS chunk_id,
            c.document_id,
            d.title,
            d.filename,
            c.chunk_index,
            c.text,
            c.page_start,
            c.page_end,
            ts_rank_cd(c.search_vector, search_query.tsq)
                AS keyword_score,
            c.section_title,
            c.table_row
        FROM chunks AS c
        JOIN documents AS d ON d.id = c.document_id
        CROSS JOIN search_query
        WHERE c.search_vector @@ search_query.tsq
    """

    params: list = [query]

    if document_id is not None:
        sql += " AND c.document_id = %s"
        params.append(document_id)

    if document_ids is not None:
        sql += " AND c.document_id = ANY(%s::bigint[])"
        params.append(document_ids)

    if workspace_id is not None:
        sql += """ AND EXISTS (
            SELECT 1 FROM workspace_documents wd
            WHERE wd.document_id = c.document_id AND wd.workspace_id = %s
        )"""
        params.append(workspace_id)

    sql += """
        ORDER BY keyword_score DESC, c.id ASC
        LIMIT %s
    """
    params.append(limit)

    with get_connection() as conn:
        rows = conn.execute("""
            WITH search_query AS (SELECT websearch_to_tsquery('english', %s) AS tsq)
        """ + sql, params).fetchall()
        if not rows and allow_partial and not EXPLICIT_SEARCH.search(query):
            rows = conn.execute("""
                WITH search_query AS (
                    SELECT replace(plainto_tsquery('english', %s)::text, ' & ', ' | ')::tsquery AS tsq
                )
            """ + sql, params).fetchall()

    return [
        {
            "chunk_id": row[0],
            "document_id": row[1],
            "title": row[2],
            "filename": row[3],
            "chunk_index": row[4],
            "text": row[5],
            "page_start": row[6],
            "page_end": row[7],
            "keyword_score": float(row[8]),
            "section_title": row[9],
            "table_row": row[10],
        }
        for row in rows
    ]
