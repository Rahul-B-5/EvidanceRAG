"""Collections organize documents by reference within a library scope."""

from psycopg.rows import dict_row

from app.db.connection import get_connection

VISIBLE_MEMBER = """(c.workspace_id IS NULL OR EXISTS (
    SELECT 1 FROM workspace_documents w
    WHERE w.workspace_id=c.workspace_id AND w.document_id=m.document_id
))"""


def collection_list(workspace_id: int | None) -> list[dict]:
    with get_connection() as conn, conn.cursor(row_factory=dict_row) as cursor:
        return cursor.execute(f"""
            SELECT c.id, c.name, c.workspace_id, COUNT(m.document_id) AS document_count
            FROM collections c LEFT JOIN collection_documents m
                ON m.collection_id=c.id AND {VISIBLE_MEMBER}
            WHERE c.workspace_id IS NOT DISTINCT FROM %s::bigint
            GROUP BY c.id ORDER BY LOWER(c.name), c.id
        """, (workspace_id,)).fetchall()


def collection_detail(collection_id: int) -> dict | None:
    with get_connection() as conn, conn.cursor(row_factory=dict_row) as cursor:
        row = cursor.execute("SELECT id, name, workspace_id FROM collections WHERE id=%s", (collection_id,)).fetchone()
        if row is None:
            return None
        members = cursor.execute(f"""
            SELECT m.document_id FROM collection_documents m JOIN collections c ON c.id=m.collection_id
            WHERE m.collection_id=%s AND {VISIBLE_MEMBER}
            ORDER BY m.created_at, m.document_id
        """, (collection_id,)).fetchall()
        return {**row, "document_ids": [m["document_id"] for m in members], "document_count": len(members)}


def create_collection(workspace_id: int | None, name: str) -> dict:
    with get_connection() as conn, conn.cursor(row_factory=dict_row) as cursor:
        return cursor.execute("""
            INSERT INTO collections(workspace_id,name) VALUES (%s,%s)
            RETURNING id,name,workspace_id,0 AS document_count
        """, (workspace_id, name)).fetchone()


def rename_collection(collection_id: int, name: str) -> bool:
    with get_connection() as conn:
        return conn.execute("""
            UPDATE collections SET name=%s,updated_at=NOW() WHERE id=%s
        """, (name, collection_id)).rowcount == 1


def change_collection_membership(collection_id: int, document_id: int, attach: bool) -> str:
    with get_connection() as conn:
        row = conn.execute("SELECT workspace_id FROM collections WHERE id=%s FOR KEY SHARE", (collection_id,)).fetchone()
        if row is None:
            return "missing_collection"
        if conn.execute("SELECT 1 FROM documents WHERE id=%s FOR KEY SHARE", (document_id,)).fetchone() is None:
            return "missing_document"
        if attach and row[0] is not None:
            if conn.execute("""
                SELECT 1 FROM workspace_documents WHERE workspace_id=%s AND document_id=%s FOR KEY SHARE
            """, (row[0], document_id)).fetchone() is None:
                return "outside_workspace"
        if attach:
            conn.execute("""
                INSERT INTO collection_documents(collection_id,document_id) VALUES (%s,%s)
                ON CONFLICT DO NOTHING
            """, (collection_id, document_id))
        else:
            conn.execute("DELETE FROM collection_documents WHERE collection_id=%s AND document_id=%s",
                         (collection_id, document_id))
        return "ok"
