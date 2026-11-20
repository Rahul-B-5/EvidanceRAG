"""Run automated UI regressions using synthetic browser fixtures and isolated storage."""

import os
import socket
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import pymupdf
from psycopg import sql
from psycopg.conninfo import make_conninfo

from app.core.config import get_settings
from app.db.connection import get_connection
from app.db.migrations import apply_migrations_in_transaction
from evaluation.database import BROWSER_TABLES, assert_isolated, fresh_schema, prepare_schema

ROOT = Path(__file__).resolve().parents[1]


def fixture_pdf(path: Path) -> None:
    with pymupdf.open() as document:
        document.set_metadata({"title": "EvidenceRAG browser fixture"})
        document.new_page().draw_rect(pymupdf.Rect(54, 54, 220, 60), color=(0.1, 0.2, 0.4), fill=(0.1, 0.2, 0.4))
        document.new_page().insert_text((54, 54), "The held-out sample size was 37 observations.")
        document.save(path)


def available_ports() -> tuple[int, int]:
    with socket.socket() as api, socket.socket() as web:
        for listener in (api, web):
            listener.bind(("127.0.0.1", 0))
        return api.getsockname()[1], web.getsockname()[1]


def run_browser_tests() -> int:
    schema = fresh_schema()
    with TemporaryDirectory(prefix="evidencerag-browser-") as workdir:
        root = Path(workdir)
        fixture_pdf(root / "browser-fixture.pdf")
        api_port, web_port = available_ports()
        with get_connection() as conn:
            prepare_schema(conn, schema)
            apply_migrations_in_transaction(conn)
            assert_isolated(conn, schema, BROWSER_TABLES)
        try:
            env = {
                **os.environ,
                "DATABASE_URL": make_conninfo(get_settings().database_url, options=f"-c search_path={schema},public"),
                "UPLOAD_DIR": str(root / "uploads"),
                "CORS_ORIGINS": f"http://127.0.0.1:{web_port}",
                "EMBEDDING_MODEL": "evidencerag-browser-fixture",
                "EMBEDDING_DIMENSIONS": "3",
                "CHUNK_SIZE": "1800",
                "CHUNK_OVERLAP": "0",
                "GENERATION_API_KEY": "",
                "GEMINI_API_KEY": "",
                "EVIDENCERAG_E2E_PYTHON": sys.executable,
                "EVIDENCERAG_E2E_SCHEMA": schema,
                "EVIDENCERAG_E2E_TEMP": str(root),
                "EVIDENCERAG_E2E_API_PORT": str(api_port),
                "EVIDENCERAG_E2E_WEB_PORT": str(web_port),
            }
            return subprocess.run(["npm", "run", "test:e2e"], cwd=ROOT / "frontend", env=env, check=False).returncode
        finally:
            with get_connection() as conn:
                conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


if __name__ == "__main__":
    raise SystemExit(run_browser_tests())
