
import psycopg
from pgvector.psycopg import register_vector
from psycopg.types.json import Jsonb

from app.core.config import get_settings


def insert_document(
    conn: psycopg.Connection,
    *,
    title: str,
    filename: str,
    file_hash: str,
    authors: list[str] | None = None,
    publication_year: int | None = None,
    stored_path: str | None = None,
    file_size_bytes: int | None = None,
    page_count: int | None = None,
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
            file_hash,
            stored_path,
            file_size_bytes,
            page_count,
            processing_status,
            processed_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'ready', NOW())
        ON CONFLICT (file_hash) DO NOTHING
        RETURNING id
        """,
        (
            title,
            authors or [],
            publication_year,
            filename,
            file_hash,
            stored_path,
            file_size_bytes,
            page_count,
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

    settings = get_settings()
    register_vector(conn)

    rows = []

    for chunk, embedding in zip(chunks, embeddings):
        if len(embedding) != settings.embedding_dimensions:
            raise ValueError(
                "Embedding dimension does not match the active profile: "
                f"expected {settings.embedding_dimensions}, got {len(embedding)}."
            )

        rows.append(
            (
                document_id,
                chunk["chunk_index"],
                chunk["text"],
                chunk["page_start"],
                chunk["page_end"],
                embedding,
                settings.embedding_model,
                settings.embedding_dimensions,
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
                embedding,
                embedding_model,
                embedding_dimensions
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
        rows,
    )


    return len(rows)


def list_documents(conn: psycopg.Connection, document_id: int | None = None) -> list[dict]:
    """Return library metadata without loading document content or embeddings."""
    rows = conn.execute(
        """
        SELECT
            d.id, d.title, d.authors, d.publication_year, d.filename,
            d.stored_path, d.file_size_bytes, d.page_count,
            d.processing_status, d.processing_error, d.processed_at,
            d.created_at, count(c.id) AS chunk_count, d.doi, d.venue, d.tags, d.metadata_revision
        FROM documents AS d
        LEFT JOIN chunks AS c ON c.document_id = d.id
        WHERE (%s::bigint IS NULL OR d.id=%s)
        GROUP BY d.id
        ORDER BY d.created_at DESC, d.id DESC
        """, (document_id, document_id),
    ).fetchall()

    return [
        {
            "id": row[0],
            "title": row[1],
            "authors": row[2],
            "publication_year": row[3],
            "filename": row[4],
            "has_stored_source": bool(row[5]),
            "file_size_bytes": row[6],
            "page_count": row[7],
            "processing_status": row[8],
            "processing_error": row[9],
            "processed_at": row[10],
            "created_at": row[11],
            "chunk_count": row[12],
            "doi": row[13],
            "venue": row[14],
            "tags": row[15],
            "metadata_revision": row[16],
        }
        for row in rows
    ]


def get_document_source_path(conn: psycopg.Connection, document_id: int) -> str | None:
    """Return the persisted source path for a document, if one exists."""
    row = conn.execute(
        "SELECT stored_path FROM documents WHERE id = %s", (document_id,)
    ).fetchone()
    return None if row is None else row[0]


def get_document(conn: psycopg.Connection, document_id: int) -> dict | None:
    """Return document metadata and processing state for a detail view."""
    return next(iter(list_documents(conn, document_id)), None)


def update_document_metadata(conn: psycopg.Connection, document_id: int, revision: int, *,
                             title: str, authors: list[str], publication_year: int | None,
                             doi: str | None, venue: str | None, tags: list[str]) -> dict | None:
    row = conn.execute("""
        UPDATE documents
        SET title=%s, authors=%s, publication_year=%s, doi=%s, venue=%s, tags=%s,
            metadata_revision=metadata_revision+1
        WHERE id=%s AND metadata_revision=%s RETURNING id
    """, (title, authors, publication_year, doi, venue, tags, document_id, revision)).fetchone()
    return get_document(conn, document_id) if row is not None else None


def delete_document(conn: psycopg.Connection, document_id: int) -> tuple[bool, str | None]:
    """Delete a document and cascaded chunks; return its now-unreferenced source."""
    deleted = conn.execute(
        "DELETE FROM documents WHERE id = %s RETURNING stored_path", (document_id,)
    ).fetchone()
    if deleted is None:
        return False, None

    stored_path = deleted[0]
    if not stored_path:
        return True, None

    still_referenced = conn.execute(
        "SELECT EXISTS(SELECT 1 FROM documents WHERE stored_path = %s)",
        (stored_path,),
    ).fetchone()[0]
    return True, None if still_referenced else stored_path


def get_document_hash(conn: psycopg.Connection, document_id: int) -> str | None:
    row = conn.execute("SELECT file_hash FROM documents WHERE id = %s", (document_id,)).fetchone()
    return row[0] if row else None


def create_conversation(
    conn: psycopg.Connection, *, title: str, document_id: int | None = None,
    workspace_id: int | None = None, document_ids: list[int] | None = None,
) -> dict:
    row = conn.execute(
        """
        INSERT INTO conversations (title, document_id)
        VALUES (%s, %s)
        RETURNING id, title, document_id, created_at, updated_at
        """,
        (title, document_id),
    ).fetchone()
    conn.execute(
        """INSERT INTO conversation_scopes (conversation_id, document_id, workspace_id, document_ids)
           VALUES (%s, %s, %s, %s)""",
        (row[0], document_id, workspace_id, document_ids),
    )
    return {
        "id": row[0], "title": row[1], "document_id": row[2],
        "workspace_id": workspace_id, "document_ids": document_ids,
        "created_at": row[3], "updated_at": row[4],
        "messages": [],
    }


def get_conversation(conn: psycopg.Connection, conversation_id: int) -> dict | None:
    row = conn.execute(
        "SELECT id, title, document_id, created_at, updated_at FROM conversations WHERE id = %s",
        (conversation_id,),
    ).fetchone()
    if row is None:
        return None
    scope = conn.execute(
        "SELECT document_id, workspace_id, document_ids FROM conversation_scopes WHERE conversation_id = %s",
        (conversation_id,),
    ).fetchone()
    messages = conn.execute(
        """
        SELECT id, role, content, citations, created_at
        FROM messages WHERE conversation_id = %s ORDER BY created_at, id
        """,
        (conversation_id,),
    ).fetchall()
    return {
        "id": row[0], "title": row[1], "document_id": scope[0] if scope else row[2],
        "workspace_id": scope[1] if scope else None,
        "document_ids": scope[2] if scope else None,
        "created_at": row[3], "updated_at": row[4],
        "messages": [
            {"id": item[0], "role": item[1], "content": item[2],
             "citations": item[3], "created_at": item[4]}
            for item in messages
        ],
    }


def add_message(
    conn: psycopg.Connection, *, conversation_id: int, role: str,
    content: str, citations: list[dict] | None = None,
) -> dict:
    row = conn.execute(
        """
        INSERT INTO messages (conversation_id, role, content, citations)
        VALUES (%s, %s, %s, %s)
        RETURNING id, role, content, citations, created_at
        """,
        (conversation_id, role, content, Jsonb(citations or [])),
    ).fetchone()
    conn.execute("UPDATE conversations SET updated_at = NOW() WHERE id = %s", (conversation_id,))
    return {"id": row[0], "role": row[1], "content": row[2], "citations": row[3], "created_at": row[4]}


def list_workspaces(conn: psycopg.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT w.id, w.name, w.description, w.created_at, w.updated_at,
               count(wd.document_id) AS document_count
        FROM workspaces w
        LEFT JOIN workspace_documents wd ON wd.workspace_id = w.id
        GROUP BY w.id ORDER BY w.updated_at DESC, w.id DESC
        """
    ).fetchall()
    return [
        {"id": row[0], "name": row[1], "description": row[2],
         "created_at": row[3], "updated_at": row[4], "document_count": row[5]}
        for row in rows
    ]


def create_workspace(conn: psycopg.Connection, *, name: str, description: str | None) -> dict:
    row = conn.execute(
        """
        INSERT INTO workspaces (name, description) VALUES (%s, %s)
        RETURNING id, name, description, created_at, updated_at
        """, (name, description)
    ).fetchone()
    return {"id": row[0], "name": row[1], "description": row[2],
            "created_at": row[3], "updated_at": row[4], "document_count": 0}


def get_workspace(conn: psycopg.Connection, workspace_id: int) -> dict | None:
    row = conn.execute(
        "SELECT id, name, description, created_at, updated_at FROM workspaces WHERE id = %s",
        (workspace_id,)
    ).fetchone()
    if row is None:
        return None
    documents = conn.execute(
        """
        SELECT d.id, d.title, d.filename, d.processing_status, wd.added_at
        FROM workspace_documents wd JOIN documents d ON d.id = wd.document_id
        WHERE wd.workspace_id = %s ORDER BY wd.added_at DESC, d.id DESC
        """, (workspace_id,)
    ).fetchall()
    return {"id": row[0], "name": row[1], "description": row[2],
            "created_at": row[3], "updated_at": row[4],
            "documents": [{"id": item[0], "title": item[1], "filename": item[2],
                           "processing_status": item[3], "added_at": item[4]}
                          for item in documents]}


def add_document_to_workspace(
    conn: psycopg.Connection, *, workspace_id: int, document_id: int
) -> bool:
    result = conn.execute(
        """
        INSERT INTO workspace_documents (workspace_id, document_id)
        VALUES (%s, %s) ON CONFLICT DO NOTHING RETURNING workspace_id
        """, (workspace_id, document_id)
    ).fetchone()
    if result is not None:
        conn.execute("UPDATE workspaces SET updated_at = NOW() WHERE id = %s", (workspace_id,))
        return True
    return False
