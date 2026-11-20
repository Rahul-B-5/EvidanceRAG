"""Durable, single-worker comparison orchestration for the local service."""

from uuid import UUID, uuid4

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app.core.config import get_settings
from app.db.connection import get_connection
from research.structured import comparison_result, extract_paper

RUN_FIELDS = "id, workspace_id, document_ids, titles, status, created_at, updated_at, error"


def expire_runs(conn) -> None:
    conn.execute("""
        UPDATE comparison_runs SET status='interrupted', error='The comparison worker stopped responding.',
            updated_at=NOW()
        WHERE status IN ('queued', 'running') AND lease_until < NOW()
    """)


def create_run(titles: dict[int, str], workspace_id: int | None) -> dict | None:
    with get_connection() as conn, conn.cursor(row_factory=dict_row) as cursor:
        expire_runs(conn)
        return cursor.execute(f"""
            INSERT INTO comparison_runs(id, workspace_id, document_ids, titles, lease_until)
            VALUES (%s,%s,%s,%s,NOW() + INTERVAL '60 seconds')
            ON CONFLICT DO NOTHING RETURNING {RUN_FIELDS}
        """, (uuid4(), workspace_id, list(titles), list(titles.values()))).fetchone()


def run_details(run_id: UUID) -> dict | None:
    with get_connection() as conn, conn.cursor(row_factory=dict_row) as cursor:
        expire_runs(conn)
        row = cursor.execute(f"SELECT {RUN_FIELDS}, papers FROM comparison_runs WHERE id=%s", (run_id,)).fetchone()
        if row is not None:
            row["result"] = comparison_result(row.pop("papers"))
        return row


def list_runs(workspace_id: int | None) -> list[dict]:
    with get_connection() as conn, conn.cursor(row_factory=dict_row) as cursor:
        expire_runs(conn)
        return cursor.execute(f"""
            SELECT {RUN_FIELDS} FROM comparison_runs r
            WHERE r.workspace_id IS NOT DISTINCT FROM %s::bigint
              AND (r.workspace_id IS NULL OR NOT EXISTS (
                SELECT 1 FROM unnest(r.document_ids) AS claimed(document_id)
                WHERE NOT EXISTS (
                    SELECT 1 FROM workspace_documents m
                    WHERE m.workspace_id=r.workspace_id AND m.document_id=claimed.document_id
                )
              ))
            ORDER BY created_at DESC LIMIT 30
        """, (workspace_id,)).fetchall()


def cancel_run(run_id: UUID) -> bool:
    with get_connection() as conn:
        expire_runs(conn)
        return conn.execute("""
            UPDATE comparison_runs SET status='cancelled', updated_at=NOW()
            WHERE id=%s AND status IN ('queued', 'running')
        """, (run_id,)).rowcount > 0


def execute_run(run_id: UUID, titles: dict[int, str], workspace_id: int | None) -> None:
    # No database transaction remains open while waiting for a model response.
    lease = int(get_settings().generation_timeout_seconds) + 90
    with get_connection() as conn:
        # Ignore duplicate scheduling and a queued run cancelled before launch.
        if conn.execute("""
            UPDATE comparison_runs SET status='running', updated_at=NOW(),
                lease_until=NOW() + %s * INTERVAL '1 second'
            WHERE id=%s AND status='queued' AND lease_until >= NOW()
        """, (lease, run_id)).rowcount != 1:
            return
    try:
        for document_id, title in titles.items():
            with get_connection() as conn:
                row = conn.execute("SELECT status FROM comparison_runs WHERE id=%s", (run_id,)).fetchone()
                if row != ("running",):
                    return
                if workspace_id is not None and conn.execute("""
                    SELECT 1 FROM workspace_documents WHERE workspace_id=%s AND document_id=%s
                """, (workspace_id, document_id)).fetchone() is None:
                    raise RuntimeError("A paper was removed from the comparison workspace.")
            paper = extract_paper(document_id, title, workspace_id)
            with get_connection() as conn:
                updated = conn.execute("""
                    UPDATE comparison_runs SET papers=papers || %s::jsonb, updated_at=NOW(),
                        lease_until=NOW() + %s * INTERVAL '1 second'
                    WHERE id=%s AND status='running' AND lease_until >= NOW()
                """, (Jsonb([paper]), lease, run_id))
                if updated.rowcount != 1:
                    return
    except Exception as exc:
        # Provider RuntimeErrors use curated messages; unexpected exceptions can
        # include credentials or snippets and are kept out of the record.
        error = str(exc) if type(exc) is RuntimeError else "Comparison stopped unexpectedly."
        with get_connection() as conn:
            conn.execute("""
                UPDATE comparison_runs SET status='failed', error=%s, updated_at=NOW()
                WHERE id=%s AND status='running'
            """, (error, run_id))
        return
    with get_connection() as conn:
        conn.execute("""
            UPDATE comparison_runs SET status='completed', updated_at=NOW()
            WHERE id=%s AND status='running'
        """, (run_id,))
