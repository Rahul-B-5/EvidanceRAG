
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = PROJECT_ROOT / "app" / "db" / "schema.sql"

# Allow `python scripts/init_db.py` from any working directory without
# requiring callers to set PYTHONPATH manually.
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.db.connection import get_connection
from app.db.migrations import apply_migrations


def initialize_database() -> None:
    schema = SCHEMA_PATH.read_text(encoding="utf-8")

    with get_connection() as conn:
        chunks_exist = conn.execute(
            "SELECT to_regclass('public.chunks') IS NOT NULL"
        ).fetchone()[0]

        if chunks_exist:
            # Upgrade installations created by the original fixed-384 schema.
            # `vector` without a typmod permits model changes; profile columns
            # keep incompatible vector spaces isolated at query time.
            conn.execute(
                "ALTER TABLE documents ADD COLUMN IF NOT EXISTS stored_path TEXT"
            )
            conn.execute(
                "ALTER TABLE documents ADD COLUMN IF NOT EXISTS file_size_bytes BIGINT"
            )
            conn.execute(
                "ALTER TABLE documents ADD COLUMN IF NOT EXISTS page_count INTEGER"
            )
            conn.execute(
                "ALTER TABLE documents ADD COLUMN IF NOT EXISTS processing_status TEXT"
            )
            conn.execute(
                "ALTER TABLE documents ADD COLUMN IF NOT EXISTS processing_error TEXT"
            )
            conn.execute(
                "ALTER TABLE documents ADD COLUMN IF NOT EXISTS processed_at TIMESTAMPTZ"
            )
            conn.execute(
                """
                UPDATE documents
                SET processing_status = COALESCE(processing_status, 'ready'),
                    processed_at = COALESCE(processed_at, created_at)
                """
            )
            conn.execute(
                "ALTER TABLE documents ALTER COLUMN processing_status SET NOT NULL"
            )
            conn.execute(
                "ALTER TABLE chunks ADD COLUMN IF NOT EXISTS embedding_model TEXT"
            )
            conn.execute(
                "ALTER TABLE chunks ADD COLUMN IF NOT EXISTS embedding_dimensions INTEGER"
            )
            conn.execute(
                "ALTER TABLE chunks ALTER COLUMN embedding TYPE vector USING embedding::vector"
            )
            conn.execute(
                """
                UPDATE chunks
                SET embedding_model = COALESCE(
                        embedding_model, 'sentence-transformers/all-MiniLM-L6-v2'
                    ),
                    embedding_dimensions = COALESCE(embedding_dimensions, 384)
                """
            )
            conn.execute(
                "ALTER TABLE chunks ALTER COLUMN embedding_model SET NOT NULL"
            )
            conn.execute(
                "ALTER TABLE chunks ALTER COLUMN embedding_dimensions SET NOT NULL"
            )
            conn.execute(
                """
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_constraint
                        WHERE conname = 'valid_embedding_dimensions'
                          AND conrelid = 'chunks'::regclass
                    ) THEN
                        ALTER TABLE chunks ADD CONSTRAINT valid_embedding_dimensions
                            CHECK (embedding_dimensions > 0);
                    END IF;

                    IF NOT EXISTS (
                        SELECT 1 FROM pg_constraint
                        WHERE conname = 'embedding_matches_dimensions'
                          AND conrelid = 'chunks'::regclass
                    ) THEN
                        ALTER TABLE chunks ADD CONSTRAINT embedding_matches_dimensions
                            CHECK (
                                embedding IS NULL
                                OR vector_dims(embedding) = embedding_dimensions
                            );
                    END IF;
                END $$;
                """
            )
            conn.execute(
                """
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_constraint
                        WHERE conname = 'valid_processing_status'
                          AND conrelid = 'documents'::regclass
                    ) THEN
                        ALTER TABLE documents ADD CONSTRAINT valid_processing_status
                            CHECK (processing_status IN ('pending', 'ready', 'failed'));
                    END IF;
                END $$;
                """
            )

        conn.execute(schema, prepare=False)

    apply_migrations()
    print("EvidenceRAG database schema initialized successfully.")


if __name__ == "__main__":
    initialize_database()
