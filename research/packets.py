"""Versioned research drafts assembled from authoritative saved passages."""

from uuid import UUID, uuid4

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app.db.connection import get_connection

FIELDS = "id, workspace_id, title, question, narrative, items, document_ids, revision, created_at, updated_at"
VISIBLE = """(workspace_id IS NULL OR NOT EXISTS (
    SELECT 1 FROM unnest(document_ids) AS source(document_id)
    WHERE NOT EXISTS (
        SELECT 1 FROM workspace_documents membership
        WHERE membership.workspace_id=evidence_packets.workspace_id
          AND membership.document_id=source.document_id
    )
))"""


def create_packet(workspace_id: int | None, title: str, question: str, chunk_ids: list[int]) -> dict | None:
    with get_connection() as conn, conn.cursor(row_factory=dict_row) as cursor:
        items = cursor.execute("""
            SELECT s.chunk_id, s.document_id, s.title, s.page_start, s.page_end,
                   s.passage, s.note, s.saved_at::text, COALESCE(d.authors, '{}') AS authors, d.publication_year
            FROM saved_evidence s LEFT JOIN documents d ON d.id=s.document_id
            WHERE s.chunk_id=ANY(%s) ORDER BY array_position(%s::bigint[], s.chunk_id)
        """, (chunk_ids, chunk_ids)).fetchall()
        if len(items) != len(chunk_ids):
            return None
        ids = sorted({item["document_id"] for item in items})
        if workspace_id is not None:
            members = cursor.execute("""
                SELECT document_id FROM workspace_documents
                WHERE workspace_id=%s AND document_id=ANY(%s)
                ORDER BY document_id FOR KEY SHARE
            """, (workspace_id, ids)).fetchall()
            if len(members) != len(ids):
                return None
        return cursor.execute(f"""
            INSERT INTO evidence_packets(id, workspace_id, title, question, items, document_ids)
            VALUES (%s,%s,%s,%s,%s,%s) RETURNING {FIELDS}
        """, (uuid4(), workspace_id, title, question, Jsonb(items), ids)).fetchone()


def list_packets(workspace_id: int | None) -> list[dict]:
    with get_connection() as conn, conn.cursor(row_factory=dict_row) as cursor:
        return cursor.execute(f"""
            SELECT id, title, revision, updated_at, jsonb_array_length(items) AS item_count
            FROM evidence_packets WHERE workspace_id IS NOT DISTINCT FROM %s::bigint AND {VISIBLE}
            ORDER BY updated_at DESC LIMIT 50
        """, (workspace_id,)).fetchall()


def packet_detail(packet_id: UUID) -> dict | None:
    with get_connection() as conn, conn.cursor(row_factory=dict_row) as cursor:
        return cursor.execute(f"SELECT {FIELDS} FROM evidence_packets WHERE id=%s AND {VISIBLE}", (packet_id,)).fetchone()


def edit_packet(packet_id: UUID, revision: int, title: str, question: str, narrative: str) -> dict | None:
    with get_connection() as conn, conn.cursor(row_factory=dict_row) as cursor:
        return cursor.execute(f"""
            UPDATE evidence_packets SET title=%s, question=%s, narrative=%s,
                revision=revision+1, updated_at=NOW()
            WHERE id=%s AND revision=%s AND {VISIBLE} RETURNING {FIELDS}
        """, (title, question, narrative, packet_id, revision)).fetchone()
