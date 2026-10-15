
import psycopg
from pgvector.psycopg import register_vector


def insert_document(
    conn: psycopg.Connection,
    *,
    title: str,
    filename: str,
    file_hash: str,
    authors: list[str] | None = None,
    publication_year: int | None = None,
) -> tuple[int, bool]:
    """
    Insert a document if its file hash is new.

    Returns:
        (document_id, created)
        created is False when this file was already in the database.
    """
    result = conn.execute(
        """
        INSERT INTO documents (
            title,
            authors,
            publication_year,
            filename,
            file_hash
        )
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (file_hash) DO NOTHING
        RETURNING id
        """,
        (
            title,
            authors or [],
            publication_year,
            filename,
            file_hash,
        ),
    ).fetchone()

    if result is not None:
        return result[0], True

    existing = conn.execute(
        "SELECT id FROM documents WHERE file_hash = %s",
        (file_hash,),
    ).fetchone()

    if existing is None:
        raise RuntimeError("Document conflict occurred, but no document was found.")

    return existing[0], False


def insert_chunks(
    conn: psycopg.Connection,
    *,
    document_id: int,
    chunks: list[dict],
    embeddings: list[list[float]],
) -> int:
    """Insert chunks and their embedding vectors for a document."""
    if len(chunks) != len(embeddings):
        raise ValueError("Each chunk must have exactly one embedding.")

    if not chunks:
        return 0

    register_vector(conn)

    rows = []

    for chunk, embedding in zip(chunks, embeddings):
        if len(embedding) != 384:
            raise ValueError(
                f"Expected 384 embedding dimensions, got {len(embedding)}."
            )

        rows.append(
            (
                document_id,
                chunk["chunk_index"],
                chunk["text"],
                chunk["page_start"],
                chunk["page_end"],
                embedding,
            )
        )


    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO chunks (
                document_id,
                chunk_index,
                text,
                page_start,
                page_end,
                embedding
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
        rows,
    )


    return len(rows)
