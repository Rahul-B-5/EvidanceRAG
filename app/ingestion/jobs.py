"""Restart-safe PDF import queue with an immutable staged file per job."""

import logging
import os
from pathlib import Path
from uuid import UUID, uuid4

from psycopg import Error
from psycopg.rows import dict_row

from app.core.config import get_settings
from app.db.connection import get_connection
from app.ingestion.pipeline import ingest_pdf
from fastapi import UploadFile

logger = logging.getLogger(__name__)
QUEUE_LOCK = 4961340
FIELDS = "id,filename,state,document_id,error,retryable,attempts,created_at,updated_at"


class UploadTooLarge(ValueError):
    pass


def upload_name(filename: str | None) -> str:
    name = Path((filename or "").replace("\\", "/")).name
    if "\x00" in name or len(name.encode()) > 240 or Path(name).suffix.lower() != ".pdf":
        raise ValueError("Only PDF files with a valid filename are supported.")
    return name


def stage_path(job: UUID, name: str) -> Path:
    if upload_name(name) != name:
        raise ValueError("Invalid staged filename.")
    root = get_settings().upload_dir.resolve()
    path = root / ".imports" / str(job) / name
    if path.resolve() != path:
        raise ValueError("Invalid staged file location.")
    return path


def enqueue(file: UploadFile) -> dict:
    name = upload_name(file.filename)
    maximum = get_settings().max_upload_mb * 1024 * 1024
    job = uuid4()
    path = stage_path(job, name)
    path.parent.mkdir(parents=True, mode=0o700, exist_ok=False)
    ready_for_commit = False
    try:
        written = 0
        with path.open("xb") as output:
            while block := file.file.read(1024 * 1024):
                written += len(block)
                if written > maximum:
                    raise UploadTooLarge(f"PDF exceeds the configured {get_settings().max_upload_mb} MB limit.")
                output.write(block)
            if not written:
                raise ValueError("The uploaded PDF is empty.")
            output.flush()
            os.fsync(output.fileno())
        with get_connection() as conn, conn.cursor(row_factory=dict_row) as cursor:
            result = cursor.execute(f"""
                INSERT INTO import_jobs(id,filename) VALUES (%s,%s) RETURNING {FIELDS}
            """, (job,name)).fetchone()
            ready_for_commit = True
        return result
    finally:
        # An uncertain commit may have published the job. Keep its input
        # available rather than risk leaving a committed job with no file.
        if not ready_for_commit:
            remove_stage(path)


def remove_stage(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
        path.parent.rmdir()
    except OSError:
        logger.warning("Unable to remove a staged import file.")


def list_jobs() -> list[dict]:
    with get_connection() as conn, conn.cursor(row_factory=dict_row) as cursor:
        return cursor.execute(f"""
            SELECT {FIELDS} FROM import_jobs ORDER BY
                (state IN ('queued','indexing')) DESC, created_at DESC,id DESC LIMIT 100
        """).fetchall()


def retry_job(job_id: UUID) -> dict | None:
    with get_connection() as conn, conn.cursor(row_factory=dict_row) as cursor:
        job = cursor.execute("SELECT filename FROM import_jobs WHERE id=%s AND state='failed' AND retryable FOR UPDATE",
                             (job_id,)).fetchone()
        if job is None:
            return None
        try:
            path = stage_path(job_id,job["filename"])
        except ValueError:
            return None
        if not path.is_file():
            return None
        return cursor.execute(f"""
            UPDATE import_jobs SET state='queued', error=NULL, retryable=FALSE, interruptions=0, updated_at=NOW()
            WHERE id=%s RETURNING {FIELDS}
        """, (job_id,)).fetchone()


def process_next_job() -> bool:
    # The session lock is released by PostgreSQL if the worker exits. Only
    # its current holder may retry indexing rows left behind by another worker.
    with get_connection() as conn:
        if not conn.execute("SELECT pg_try_advisory_lock(%s,hashtext(current_schema()))", (QUEUE_LOCK,)).fetchone()[0]:
            return False
        conn.commit()
        with conn.transaction(), conn.cursor(row_factory=dict_row) as cursor:
            conn.execute("""
                UPDATE import_jobs SET interruptions=interruptions+1,
                  state=CASE WHEN interruptions<2 THEN 'queued' ELSE 'failed' END,
                  retryable=interruptions>=2,
                  error=CASE WHEN interruptions>=2 THEN 'Import was interrupted repeatedly. Retry to continue.' END,
                  updated_at=NOW()
                WHERE state='indexing'
            """)
            job = cursor.execute("""
                UPDATE import_jobs SET state='indexing',attempts=attempts+1,updated_at=NOW()
                WHERE id=(SELECT id FROM import_jobs WHERE state='queued' ORDER BY created_at,id LIMIT 1)
                RETURNING id,filename,attempts
            """).fetchone()
        if not job:
            return False
        path = None
        try:
            path = stage_path(job["id"],job["filename"])
            result = ingest_pdf(path)
            state = "duplicate" if result["status"] == "already_exists" else "imported"
            values = (state, result["document_id"], None, False)
        except FileNotFoundError:
            values = ("failed", None, "The staged PDF is unavailable. Upload it again.", False)
        except ValueError:
            values = ("failed", None, "Unable to index the PDF. Check that it is readable and contains text.", False)
        except (Error, OSError, RuntimeError) as exc:
            logger.warning("PDF import failed (%s).", type(exc).__name__)
            values = ("failed", None, "Indexing stopped. Retry this upload.", True)
        with conn.transaction():
            updated = conn.execute("""
                UPDATE import_jobs SET state=%s,document_id=%s,error=%s,retryable=%s,updated_at=NOW()
                WHERE id=%s AND state='indexing' AND attempts=%s
            """, (*values,job["id"],job["attempts"])).rowcount
        if updated and path and not values[3]:
            remove_stage(path)
        return True
