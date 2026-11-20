"""Run automated UI regressions using synthetic browser fixtures and isolated storage."""

import argparse
import os
import socket
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import pymupdf
from evaluation.database import isolated_database

ROOT = Path(__file__).resolve().parents[1]


def fixture_pdf(path: Path, title: str = "EvidenceRAG browser fixture", sample_size: int = 37) -> None:
    with pymupdf.open() as document:
        document.set_metadata({"title": title})
        document.new_page().draw_rect(pymupdf.Rect(54, 54, 220, 60), color=(0.1, 0.2, 0.4), fill=(0.1, 0.2, 0.4))
        page = document.new_page()
        page.insert_text((54, 54), f"The held-out sample size was {sample_size} observations.")
        page.insert_text((54, 72), "StarlingNet F1 score was 87% on OrchardBench.")
        page.insert_text((54, 90), "The random seed was 42. We used a single A100 GPU.")
        page.insert_text((54, 108), "A limitation was that we only evaluated one site and lacked external validation.")
        document.set_toc([[1, "Calibration results", 2]])
        document.save(path)


def table_fixture_pdf(path: Path) -> None:
    with pymupdf.open() as pdf:
        pdf.set_metadata({"title": "Calibration table fixture"})
        pdf.new_page().insert_text((54, 54), "The report contains a calibration table on the next page.")
        page = pdf.new_page()
        page.insert_text((54, 65), "Table 2. Calibration results")
        for x in (54, 180, 305):
            page.draw_line((x, 76), (x, 151))
        for y in (76, 101, 126, 151):
            page.draw_line((54, y), (305, y))
        for y, metric, score in (
            (92, "Metric", "Score"), (117, "Precision without tuning", "0.84"), (142, "Recall", "0.72"),
        ):
            page.insert_text((60, y), metric)
            page.insert_text((186, y), score)
        pdf.set_toc([[1, "Introduction", 1], [1, "Results", 2]])
        pdf.save(path)


def available_ports() -> tuple[int, int]:
    with socket.socket() as api, socket.socket() as web:
        for listener in (api, web):
            listener.bind(("127.0.0.1", 0))
        return api.getsockname()[1], web.getsockname()[1]


def run_browser_tests(screenshots: Path | None = None, grep: str | None = None) -> int:
    with TemporaryDirectory(prefix="evidencerag-browser-") as workdir, isolated_database() as (schema, database_url):
        root = Path(workdir)
        fixture_pdf(root / "browser-fixture.pdf")
        fixture_pdf(root / "browser-second.pdf", "EvidenceRAG replication fixture", 42)
        table_fixture_pdf(root / "browser-table.pdf")
        api_port, web_port = available_ports()
        env = {
            **os.environ,
            "DATABASE_URL": database_url,
            "UPLOAD_DIR": str(root / "uploads"),
            "CORS_ORIGINS": f"http://127.0.0.1:{web_port}",
            "API_ALLOWED_HOSTS": "127.0.0.1",
            "EMBEDDING_MODEL": "evidencerag-browser-fixture",
            "EMBEDDING_DIMENSIONS": "3",
            "CHUNK_SIZE": "1800",
            "CHUNK_OVERLAP": "0",
            "GENERATION_API_KEY": "",
            "GEMINI_API_KEY": "",
            "GENERATION_PROVIDER": "ollama",
            "GENERATION_MODEL": "browser-fixture",
            "GENERATION_BASE_URL": "",
            "EVIDENCERAG_E2E_PYTHON": sys.executable,
            "EVIDENCERAG_E2E_SCHEMA": schema,
            "EVIDENCERAG_E2E_TEMP": str(root),
            "EVIDENCERAG_E2E_API_PORT": str(api_port),
            "EVIDENCERAG_E2E_WEB_PORT": str(web_port),
        }
        if screenshots is not None:
            screenshots.mkdir(parents=True, exist_ok=True)
            env["EVIDENCERAG_E2E_SCREENSHOTS"] = str(screenshots.resolve())
        command = ["npm", "run", "test:e2e"]
        if grep:
            command.extend(["--", "--grep", grep])
        return subprocess.run(command, cwd=ROOT / "frontend", env=env, check=False).returncode


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--screenshots", type=Path, help="Save UI screenshots from the isolated synthetic workflows.")
    parser.add_argument("--grep", help="Run only browser tests matching this Playwright expression.")
    args = parser.parse_args()
    raise SystemExit(run_browser_tests(args.screenshots, args.grep))
