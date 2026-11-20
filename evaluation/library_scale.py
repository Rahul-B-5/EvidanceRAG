"""Measure local PostgreSQL retrieval latency on a disposable synthetic library."""

import argparse
import json
import math
from collections.abc import Callable
from statistics import median
from time import perf_counter
from unittest.mock import patch

import psycopg

from app.core.config import get_settings
from app.db.repository import list_documents
from app.retrieval import keyword, vector
from app.retrieval.service import retrieve_evidence
from evaluation.database import assert_isolated, isolated_database


DIMENSIONS = 384
CHUNKS_PER_PAPER = 60
MODEL = "evidencerag-scale-fixture"
QUERY = "external calibration uncertainty observations"


def seed_library(conn: psycopg.Connection, papers: int) -> int:
    conn.execute("""
        INSERT INTO documents (title, filename, file_hash, page_count)
        SELECT 'Synthetic calibration paper ' || paper, 'fixture-' || paper || '.pdf',
               md5(paper::text) || md5('paper-' || paper), 30
        FROM generate_series(1, %s) AS paper
    """, (papers,))
    conn.execute("""
        INSERT INTO chunks (document_id, chunk_index, text, page_start, page_end,
                            embedding_model, embedding_dimensions, embedding)
        SELECT d.id, passage, CASE mod(passage, 5)
            WHEN 0 THEN repeat('External calibration uncertainty was estimated from observations. ', 12)
            WHEN 1 THEN repeat('The replication compared held-out domains and control cohorts. ', 12)
            WHEN 2 THEN repeat('The confidence interval came from a stratified bootstrap. ', 12)
            WHEN 3 THEN repeat('The experimental design measured precision, recall and latency. ', 12)
            ELSE repeat('The validation split used independent train and test groups. ', 12) END,
            passage / 2 + 1, passage / 2 + 1, %s, %s,
            (SELECT array_agg(sin(d.id * 0.37 + passage * component * 0.23)::real ORDER BY component)::vector
             FROM generate_series(1, %s) AS component)
        FROM documents AS d CROSS JOIN generate_series(0, %s - 1) AS passage
    """, (MODEL, DIMENSIONS, DIMENSIONS, CHUNKS_PER_PAPER))
    scope = conn.execute("INSERT INTO workspaces(name) VALUES ('Scale sample') RETURNING id").fetchone()[0]
    conn.execute("""
        INSERT INTO workspace_documents(workspace_id, document_id)
        SELECT %s, id FROM documents ORDER BY id LIMIT 10
    """, (scope,))
    conn.execute("ANALYZE documents")
    conn.execute("ANALYZE chunks")
    conn.execute("ANALYZE workspace_documents")
    return scope


def measure(operation: Callable[[], object], repetitions: int) -> dict:
    operation()
    elapsed = []
    for _ in range(repetitions):
        started = perf_counter()
        operation()
        elapsed.append((perf_counter() - started) * 1000)
    p95 = sorted(elapsed)[math.ceil(len(elapsed) * 0.95) - 1]
    return {"median_ms": round(median(elapsed), 1), "p95_ms": round(p95, 1)}


def evaluate_scale(papers: int, repetitions: int) -> dict:
    with isolated_database() as (schema, dsn):
        def connect() -> psycopg.Connection:
            return psycopg.connect(dsn)

        with connect() as conn:
            assert_isolated(conn, schema, ("chunks", "workspace_documents"))
            scope = seed_library(conn, papers)
            port, pg_version = conn.execute("SELECT inet_server_port(), current_setting('server_version')").fetchone()

        def library():
            with connect() as conn:
                return list_documents(conn)

        settings = get_settings().model_copy(update={"embedding_model": MODEL, "embedding_dimensions": DIMENSIONS})
        fixed_vector = [math.sin(i * 0.31) for i in range(DIMENSIONS)]
        with (patch.object(keyword, "get_connection", connect),
              patch.object(vector, "get_connection", connect),
              patch.object(vector, "get_settings", lambda: settings),
              patch.object(vector, "embed_query", lambda _: fixed_vector)):
            evidence = retrieve_evidence(QUERY, top_k=5, workspace_id=scope)["evidence"]
            if len(evidence) != 5 or any(row["document_id"] > 10 for row in evidence):
                raise RuntimeError("Workspace search returned missing or out-of-scope passages.")
            operations = {
                "library": library,
                "keyword": lambda: keyword.search_keyword(QUERY, top_k=5),
                "vector": lambda: vector.search_vector(QUERY, top_k=5),
                "hybrid": lambda: retrieve_evidence(QUERY, top_k=5),
                "hybrid_workspace": lambda: retrieve_evidence(QUERY, top_k=5, workspace_id=scope),
            }
            return {
                "papers": papers, "passages": papers * CHUNKS_PER_PAPER, "workspace_papers": min(10, papers),
                "embedding_dimensions": DIMENSIONS, "repetitions": repetitions,
                "postgres_port": port, "postgres_version": pg_version,
                "latency": {name: measure(operation, repetitions) for name, operation in operations.items()},
            }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--papers", type=int, default=250)
    parser.add_argument("--repetitions", type=int, default=20)
    args = parser.parse_args()
    if not 10 <= args.papers <= 1000 or not 5 <= args.repetitions <= 100:
        parser.error("Use 10–1000 papers and 5–100 repetitions.")
    print(json.dumps(evaluate_scale(args.papers, args.repetitions), indent=2))
