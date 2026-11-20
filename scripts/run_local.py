"""Run the local API and frontend using the existing PostgreSQL database."""

import os
import shutil
import signal
import socket
import subprocess
import sys
from pathlib import Path
from time import monotonic, sleep
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener

import psycopg

from app.core.config import get_settings
from app.db.migrations import apply_migrations_in_transaction

ROOT = Path(__file__).resolve().parents[1]
HOST = "127.0.0.1"
API_PORT = 8000
WEB_PORT = 5173


def check_port(port: int) -> None:
    with socket.socket() as listener:
        try:
            listener.bind((HOST, port))
        except OSError:
            raise RuntimeError(f"Port {port} on {HOST} is unavailable. Stop the existing listener and retry.") from None


def prepare_database() -> None:
    try:
        with psycopg.connect(get_settings().database_url, connect_timeout=5) as conn:
            if None in conn.execute("SELECT to_regclass('documents'), to_regclass('chunks')").fetchone():
                raise RuntimeError("The database has no EvidenceRAG schema. Follow the clean-install steps in README.md.")
            apply_migrations_in_transaction(conn)
    except psycopg.OperationalError:
        raise RuntimeError("Cannot connect to PostgreSQL. Start your server and check DATABASE_URL in .env.") from None
    except psycopg.Error as error:
        raise RuntimeError(f"Database migrations failed ({type(error).__name__}). Check schema permissions and pgvector.") from None


def wait_until_ready(label: str, url: str, process: subprocess.Popen) -> None:
    opener = build_opener(ProxyHandler({}))
    deadline = monotonic() + 25
    while monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"{label} exited during startup. See the process output above.")
        try:
            with opener.open(url, timeout=1) as response:
                if response.status == 200:
                    return
        except (URLError, TimeoutError):
            sleep(.2)
    raise RuntimeError(f"{label} did not become ready at {url}. See the process output above.")


def stop(process: subprocess.Popen) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait()


def main() -> int:
    children: list[subprocess.Popen] = []
    try:
        if not shutil.which("npm") or not (ROOT / "frontend/node_modules/.bin/vite").is_file():
            raise RuntimeError("Install Node 22.13+ and run npm --prefix frontend ci.")
        for port in (API_PORT, WEB_PORT):
            check_port(port)
        prepare_database()
        api_url, web_url = (f"http://{HOST}:{port}" for port in (API_PORT, WEB_PORT))
        api = subprocess.Popen([
            sys.executable, "-m", "uvicorn", "app.api.main:app",
            "--host", HOST, "--port", str(API_PORT), "--no-access-log",
        ], cwd=ROOT, start_new_session=True)
        children.append(api)
        wait_until_ready("API", api_url + "/health", api)
        frontend = subprocess.Popen(
            ["npm", "run", "dev", "--", "--port", str(WEB_PORT)], cwd=ROOT / "frontend",
            env={**os.environ, "VITE_API_URL": api_url}, start_new_session=True,
        )
        children.append(frontend)
        wait_until_ready("Frontend", web_url, frontend)
        print(f"EvidenceRAG is ready at {web_url}. Press Ctrl+C to stop.", flush=True)
        while all(child.poll() is None for child in children):
            sleep(.5)
        raise RuntimeError("A development server exited. See the process output above.")
    except KeyboardInterrupt:
        return 0
    except ValueError:
        print("Startup failed. Check the application's .env settings.", file=sys.stderr)
        return 1
    except (RuntimeError, OSError) as error:
        print(f"Startup failed. {error}", file=sys.stderr)
        return 1
    finally:
        for child in reversed(children):
            stop(child)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, lambda *_: signal.raise_signal(signal.SIGINT))
    raise SystemExit(main())
