"""Rebuild a document's vectors while preserving indexed passages and citations."""

import json
import logging
from contextlib import suppress
from uuid import UUID, uuid4

from psycopg import Connection, Error
from psycopg.rows import dict_row

from app.core.config import get_settings
from app.db.connection import get_connection
from app.retrieval.embeddings import embed_documents

logger = logging.getLogger(__name__)
JOB_FIELDS = """id, document_id, model, dimensions, total_chunks, prepared_chunks,
                status, error, created_at, updated_at"""
LEASE = "INTERVAL '5 minutes'"
BATCH_SIZE = 32


def expire_rebuilds(conn: Connection, document_id: int) -> None:
    conn.execute("""
        UPDATE embedding_rebuilds SET status='interrupted', updated_at=NOW(),
            error='The embedding worker stopped responding.'
        WHERE document_id=%s AND status IN ('queued','running') AND lease_until < NOW()
    """, (document_id,))


def embedding_status(document_id: int) -> dict | None:
    config = get_settings()
    with get_connection() as conn, conn.cursor(row_factory=dict_row) as cursor:
        expire_rebuilds(conn, document_id)
        result = cursor.execute(f"""
            SELECT vectors.*, (
                SELECT row_to_json(history) FROM (
                    SELECT {JOB_FIELDS} FROM embedding_rebuilds
                    WHERE document_id=d.id ORDER BY created_at DESC, id DESC LIMIT 1
                ) history
            ) AS job
            FROM documents d CROSS JOIN LATERAL (
                SELECT count(*) AS total_chunks, count(*) FILTER (
                    WHERE embedding IS NOT NULL AND embedding_model=%s AND embedding_dimensions=%s
                ) AS active_chunks
                FROM chunks WHERE document_id=d.id
            ) vectors WHERE d.id=%s
        """, (config.embedding_model, config.embedding_dimensions, document_id)).fetchone()
    return {**result, "model": config.embedding_model, "dimensions": config.embedding_dimensions} if result is not None else None


def queue_rebuild(document_id: int) -> tuple[dict | None, str | None]:
    config = get_settings()
    with get_connection() as conn, conn.cursor(row_factory=dict_row) as cursor:
        if conn.execute("SELECT id FROM documents WHERE id=%s FOR KEY SHARE", (document_id,)).fetchone() is None:
            return None, "missing"
        count = conn.execute("SELECT count(*) FROM chunks WHERE document_id=%s", (document_id,)).fetchone()[0]
        if not count:
            return None, "empty"
        expire_rebuilds(conn, document_id)
        job = cursor.execute(f"""
            INSERT INTO embedding_rebuilds (id, document_id, model, dimensions, total_chunks, lease_until)
            VALUES (%s,%s,%s,%s,%s,NOW() + {LEASE})
            ON CONFLICT DO NOTHING RETURNING {JOB_FIELDS}
        """, (uuid4(), document_id, config.embedding_model, config.embedding_dimensions, count)).fetchone()
    return job, None if job else "busy"


def cancel_rebuild(document_id: int, job_id: UUID) -> bool:
    with get_connection() as conn:
        expire_rebuilds(conn, document_id)
        return conn.execute("""
            UPDATE embedding_rebuilds SET status='cancelled', updated_at=NOW()
            WHERE document_id=%s AND id=%s AND status IN ('queued','running')
            RETURNING id
        """, (document_id, job_id)).fetchone() is not None


def record_failure(job_id: UUID, reason: str) -> None:
    with get_connection() as conn:
        conn.execute("""
            UPDATE embedding_rebuilds SET status='failed', error=%s, updated_at=NOW()
            WHERE id=%s AND status='running' AND lease_until>=NOW()
        """, (reason, job_id))


def execute_rebuild(job_id: UUID) -> None:
    try:
        rebuild(job_id)
    except Exception as exc:
        logger.warning("Embedding rebuild failed (%s).", type(exc).__name__)
        with suppress(Error):
            record_failure(job_id, "Unable to rebuild embeddings. Existing vectors were retained.")


def rebuild(job_id: UUID) -> None:
    with get_connection() as conn, conn.cursor(row_factory=dict_row) as cursor:
        job = cursor.execute(f"""
            UPDATE embedding_rebuilds SET status='running', updated_at=NOW(), lease_until=NOW() + {LEASE}
            WHERE id=%s AND status='queued' AND lease_until>=NOW() RETURNING {JOB_FIELDS}
        """, (job_id,)).fetchone()
        if job is None:
            return
        snapshots = conn.execute(
            "SELECT id,text FROM chunks WHERE document_id=%s ORDER BY id", (job["document_id"],),
        ).fetchall()
    config = get_settings()
    if (job["model"], job["dimensions"]) != (config.embedding_model, config.embedding_dimensions):
        record_failure(job_id, "The active embedding profile changed. Start another rebuild.")
        return
    if len(snapshots) != job["total_chunks"]:
        record_failure(job_id, "The indexed passages changed. Start another rebuild.")
        return
    prepared = []
    for start in range(0, len(snapshots), BATCH_SIZE):
        batch = snapshots[start:start + BATCH_SIZE]
        vectors = embed_documents([text for _, text in batch])
        for (chunk_id, _), coordinates in zip(batch, vectors, strict=True):
            if len(coordinates) != job["dimensions"] or not any(coordinates):
                raise ValueError("Embedding vector does not match the selected profile.")
            prepared.append((json.dumps(coordinates, allow_nan=False), job["model"], job["dimensions"], chunk_id))
        with get_connection() as conn:
            alive = conn.execute(f"""
                UPDATE embedding_rebuilds SET prepared_chunks=%s, updated_at=NOW(), lease_until=NOW() + {LEASE}
                WHERE id=%s AND status='running' AND lease_until>=NOW() RETURNING id
            """, (len(prepared), job_id)).fetchone()
            if alive is None:
                return
    publish_rebuild(job_id, job["document_id"], snapshots, prepared)


def publish_rebuild(job_id: UUID, document_id: int, snapshots: list, prepared: list) -> None:
    with get_connection() as conn:
        if conn.execute("SELECT id FROM documents WHERE id=%s FOR KEY SHARE", (document_id,)).fetchone() is None:
            return
        if conn.execute("""
            SELECT id FROM embedding_rebuilds WHERE id=%s AND status='running' AND lease_until>=NOW() FOR UPDATE
        """, (job_id,)).fetchone() is None:
            return
        current = conn.execute(
            "SELECT id,text FROM chunks WHERE document_id=%s ORDER BY id FOR UPDATE", (document_id,),
        ).fetchall()
        if current != snapshots:
            conn.execute("""
                UPDATE embedding_rebuilds SET status='failed', updated_at=NOW(),
                    error='The indexed passages changed. Start another rebuild.' WHERE id=%s
            """, (job_id,))
            return
        with conn.cursor() as cursor:
            cursor.executemany("""
                UPDATE chunks SET embedding=%s::vector, embedding_model=%s, embedding_dimensions=%s WHERE id=%s
            """, prepared)
        conn.execute("UPDATE embedding_rebuilds SET status='completed', updated_at=NOW() WHERE id=%s", (job_id,))
