
from pgvector import Vector
from pgvector.psycopg import register_vector

from app.core.config import get_settings
from app.db.connection import get_connection
from app.retrieval.embeddings import embed_query


def search_vector(
    query: str,
    top_k: int | None = None,
    document_id: int | None = None,
    workspace_id: int | None = None,
    document_ids: list[int] | None = None,
) -> list[dict]:
    """Retrieve semantically similar chunks using PostgreSQL and pgvector."""
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

    query_embedding = embed_query(query)

    if len(query_embedding) != settings.embedding_dimensions:
        raise ValueError(
            f"Expected {settings.embedding_dimensions} dimensions, "
            f"got {len(query_embedding)}."
        )

    # Build the optional document filter only when requested.
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
            1 - (c.embedding <=> %s::vector) AS similarity
        FROM chunks AS c
        JOIN documents AS d ON d.id = c.document_id
        WHERE c.embedding IS NOT NULL
          AND c.embedding_model = %s
          AND c.embedding_dimensions = %s
    """
    params = [Vector(query_embedding), settings.embedding_model, settings.embedding_dimensions]

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
        ORDER BY c.embedding <=> %s::vector
        LIMIT %s
    """
    params.extend([Vector(query_embedding), limit])

    with get_connection() as conn:
        register_vector(conn)
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
            "similarity": float(row[8]),
        }
        for row in rows
    ]
