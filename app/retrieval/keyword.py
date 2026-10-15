
from app.core.config import get_settings
from app.db.connection import get_connection


def search_keyword(
    query: str,
    top_k: int | None = None,
    document_id: int | None = None,
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

    sql = """
        WITH search_query AS (
            SELECT websearch_to_tsquery('english', %s) AS tsq
        )
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
                AS keyword_score
        FROM chunks AS c
        JOIN documents AS d ON d.id = c.document_id
        CROSS JOIN search_query
        WHERE c.search_vector @@ search_query.tsq
    """

    params: list = [query]

    if document_id is not None:
        sql += " AND c.document_id = %s"
        params.append(document_id)

    sql += """
        ORDER BY keyword_score DESC, c.id ASC
        LIMIT %s
    """
    params.append(limit)

    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()

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
        }
        for row in rows
    ]
