
from collections.abc import Iterator

import psycopg
from psycopg import Connection

from app.core.config import get_settings


def get_connection() -> Connection:
    """Open a PostgreSQL connection."""
    settings = get_settings()
    return psycopg.connect(settings.database_url)


def connection_scope() -> Iterator[Connection]:
    """
    Yield a connection and close it when the caller finishes.

    The connection context commits on successful exit and rolls back
    when an exception occurs.
    """
    with get_connection() as conn:
        yield conn
