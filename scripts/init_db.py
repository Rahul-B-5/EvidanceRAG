
from pathlib import Path

from app.db.connection import get_connection

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = PROJECT_ROOT / "app" / "db" / "schema.sql"


def initialize_database() -> None:
    schema = SCHEMA_PATH.read_text(encoding="utf-8")

    with get_connection() as conn:
        conn.execute(schema, prepare=False)

    print("EvidenceRAG database schema initialized successfully.")


if __name__ == "__main__":
    initialize_database()
