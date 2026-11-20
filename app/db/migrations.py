"""Apply additive migrations under a transaction-scoped PostgreSQL lock."""
from pathlib import Path
from psycopg import Connection

from app.db.connection import get_connection

MIGRATIONS = Path(__file__).with_name("migrations")


def apply_migrations_in_transaction(conn: Connection) -> None:
    conn.execute("SELECT pg_advisory_xact_lock(4961338)")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS evidencerag_migrations (
            version TEXT PRIMARY KEY,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    applied = {row[0] for row in conn.execute("SELECT version FROM evidencerag_migrations")}
    for migration in sorted(MIGRATIONS.glob("*.sql")):
        if migration.stem in applied:
            continue
        conn.execute(migration.read_text(encoding="utf-8"), prepare=False)
        conn.execute(
            "INSERT INTO evidencerag_migrations(version) VALUES (%s)", (migration.stem,)
        )


def apply_migrations() -> None:
    with get_connection() as conn:
        apply_migrations_in_transaction(conn)


if __name__ == "__main__":
    apply_migrations()
