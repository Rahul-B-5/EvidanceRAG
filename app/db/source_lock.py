"""Serialize source publication and removal for a single content hash."""

from hashlib import sha256

from psycopg import Connection


def lock_source(conn: Connection, file_hash: str) -> None:
    """Hold a session lock until the caller closes its dedicated connection."""
    key = int.from_bytes(sha256(file_hash.encode()).digest()[:4], "big", signed=True)
    conn.execute("SET LOCAL lock_timeout = '10s'")
    conn.execute("SELECT pg_advisory_lock(%s, %s)", (4961339, key))
    # Session locks survive commit so deletion can commit before unlinking.
    conn.commit()
