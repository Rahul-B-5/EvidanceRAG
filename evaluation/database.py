"""Create isolated evaluation tables while retaining access to public pgvector types."""

import re
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from psycopg import Connection, sql
from psycopg.conninfo import make_conninfo

from app.core.config import get_settings
from app.db.connection import get_connection
from app.db.migrations import apply_migrations_in_transaction

BASE_SCHEMA = Path(__file__).resolve().parents[1] / "app" / "db" / "schema.sql"
TEST_TABLES = ("documents", "chunks", "workspaces", "workspace_documents", "conversations", "messages", "conversation_scopes")
BROWSER_TABLES = ("evidencerag_migrations", "saved_evidence", "reader_bookmarks",
                  "evidence_packets", "collections", "collection_documents", "embedding_rebuilds",
                  "research_claims", "research_claim_assessments", "import_jobs")


def fresh_schema() -> str:
    return f"evidencerag_eval_{uuid4().hex}"


def assert_isolated(conn: Connection, schema: str, extra_tables: tuple[str, ...] = ()) -> None:
    if not re.fullmatch(r"evidencerag_eval_[0-9a-f]{32}", schema):
        raise RuntimeError("Invalid evaluation schema name.")
    if conn.execute("SELECT current_schema()").fetchone()[0] != schema:
        raise RuntimeError("The configured search path does not select the evaluation schema.")
    tables = [f"{schema}.{name}" for name in (*TEST_TABLES, *extra_tables)]
    complete = conn.execute(
        "SELECT bool_and(to_regclass(name) IS NOT NULL) FROM unnest(%s::text[]) name", (tables,)
    ).fetchone()[0]
    if not complete:
        raise RuntimeError("Evaluation schema is incomplete. No fixture rows were written.")


def prepare_schema(conn: Connection, schema: str) -> None:
    conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    conn.execute(sql.SQL("SET LOCAL search_path TO {}, public").format(sql.Identifier(schema)))
    conn.execute(BASE_SCHEMA.read_text(encoding="utf-8"), prepare=False)
    assert_isolated(conn, schema)


@contextmanager
def isolated_database() -> Iterator[tuple[str, str]]:
    """Provide a committed scratch schema for tests using several connections."""
    schema = fresh_schema()
    with get_connection() as conn:
        prepare_schema(conn, schema)
        apply_migrations_in_transaction(conn)
        assert_isolated(conn, schema, BROWSER_TABLES)
    try:
        yield schema, make_conninfo(get_settings().database_url, options=f"-c search_path={schema},public")
    finally:
        with get_connection() as conn:
            conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
