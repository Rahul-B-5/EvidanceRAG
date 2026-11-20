"""Store human judgments independently of model-selected relationships."""

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app.db.connection import get_connection


def read_reviews(finding_id: str, workspace_id: int | None) -> list[dict]:
    with get_connection() as conn, conn.cursor(row_factory=dict_row) as cursor:
        return cursor.execute("""
            SELECT candidate_chunk_id, relation, alignment, note, updated_at, candidate_snapshot
            FROM claim_reviews r
            WHERE r.scope_key=%s AND r.finding_id=%s
              AND (r.scope_key=0 OR EXISTS (
                SELECT 1 FROM workspace_documents m
                WHERE m.workspace_id=r.scope_key AND m.document_id=r.candidate_document_id
              ))
            ORDER BY updated_at DESC, candidate_chunk_id
        """, (workspace_id or 0, finding_id)).fetchall()


def write_review(finding: dict, candidate: dict, workspace_id: int | None,
                 relation: str, alignment: str, note: str) -> dict | None:
    with get_connection() as conn, conn.cursor(row_factory=dict_row) as cursor:
        if workspace_id is not None:
            # Lock membership until commit so a concurrent detach cannot cause
            # an assessment to be saved outside the current workspace.
            members = cursor.execute("""
                SELECT document_id FROM workspace_documents
                WHERE workspace_id=%s AND document_id=ANY(%s)
                ORDER BY document_id FOR KEY SHARE
            """, (workspace_id, [finding["provenance"]["document_id"], candidate["document_id"]])).fetchall()
            if len(members) != 2:
                return None
        return cursor.execute("""
            INSERT INTO claim_reviews(
                scope_key, finding_id, candidate_chunk_id, candidate_document_id,
                relation, alignment, note, finding_snapshot, candidate_snapshot
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (scope_key, finding_id, candidate_chunk_id) DO UPDATE
              SET relation=EXCLUDED.relation, alignment=EXCLUDED.alignment,
                  note=EXCLUDED.note, updated_at=NOW()
            RETURNING candidate_chunk_id, relation, alignment, note, updated_at, candidate_snapshot
        """, (workspace_id or 0, finding["id"], candidate["chunk_id"],
              candidate["document_id"], relation, alignment, note,
              Jsonb(finding), Jsonb(candidate))).fetchone()
