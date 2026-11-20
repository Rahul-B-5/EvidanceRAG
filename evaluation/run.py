"""Evaluate the actual PostgreSQL retrievers and HTTP answer contract on synthetic data."""

import argparse
import json
import re
from contextlib import ExitStack, contextmanager, nullcontext
from hashlib import sha256
from pathlib import Path
from statistics import mean, median, quantiles
from time import perf_counter
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api.main import app
from app.core.config import get_settings
from app.db.connection import get_connection
from app.generation import answerer
from app.retrieval import embeddings, fusion, keyword, vector
from evaluation.database import fresh_schema, prepare_schema

CORPUS = Path(__file__).with_name("corpus.json")
TOP_K = 4


def retrieval_metrics(ranking: list[str], expected: set[str]) -> dict:
    if not expected:
        return {"precision": None, "recall": None, "reciprocal_rank": None}
    ranks = [rank for rank, key in enumerate(ranking, start=1) if key in expected]
    return {
        "precision": len(set(ranking) & expected) / TOP_K,
        "recall": len(set(ranking) & expected) / len(expected),
        "reciprocal_rank": 1 / ranks[0] if ranks else 0.0,
    }


def latencies(values: list[float]) -> dict:
    return {"p50_ms": round(median(values), 2),
            "p95_ms": round(quantiles(values, n=20, method="inclusive")[18] if len(values) > 1 else values[0], 2)}


def contains_answer_value(answer: str, expected: str) -> bool:
    if re.fullmatch(r"\d+(?:\.\d+)?%?", expected):
        number = re.escape(expected.removesuffix("%"))
        unit = r"\s*(?:%|percent\b)" if expected.endswith("%") else ""
        return bool(re.search(r"(?<![\w.,])" + number + unit + r"(?!\w|[.,]\d)", answer, re.IGNORECASE))
    return expected.casefold() in answer.casefold()


def insert_fixtures(conn, fixture: dict, live_embeddings: bool) -> tuple:
    docs, identifiers, anchors = {}, {}, {}
    settings = get_settings()
    model = settings.embedding_model if live_embeddings else "evidencerag-evaluation"
    dimensions = settings.embedding_dimensions if live_embeddings else 4
    for document in fixture["documents"]:
        key = document["key"]
        docs[key] = conn.execute("""
            INSERT INTO documents (title, filename, file_hash) VALUES (%s,%s,%s) RETURNING id
        """, (document["title"], key + ".pdf", sha256(key.encode()).hexdigest())).fetchone()[0]
        chunks = document["chunks"]
        vectors = embeddings.embed_documents([chunk["text"] for chunk in chunks]) if live_embeddings else [
            chunk["vector"] for chunk in chunks
        ]
        for index, (item, values) in enumerate(zip(chunks, vectors, strict=True)):
            page = item["page"]
            id_ = conn.execute("""
                INSERT INTO chunks (document_id, chunk_index, text, page_start, page_end,
                                    embedding_model, embedding_dimensions, embedding)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s::vector) RETURNING id
            """, (docs[key], index, item["text"], page, page, model, dimensions, json.dumps(values))).fetchone()[0]
            identifiers[id_] = f"{key}:{index}"
            anchors[id_] = (docs[key], page, page)
    workspaces = {
        name: conn.execute("INSERT INTO workspaces(name) VALUES (%s) RETURNING id", (name,)).fetchone()[0]
        for name in fixture["workspaces"]
    }
    with conn.cursor() as cursor:
        cursor.executemany("INSERT INTO workspace_documents(workspace_id,document_id) VALUES (%s,%s)",
                           [(workspaces[name], docs[key]) for name, keys in fixture["workspaces"].items() for key in keys])
    return docs, identifiers, anchors, workspaces, SimpleNamespace(
        embedding_model=model, embedding_dimensions=dimensions, retrieval_top_k=TOP_K)


def answer_checks(response, case: dict, identifiers: dict, anchors: dict, allowed: set[int]) -> dict:
    if response.status_code != 200:
        return {"success_status": False, "abstention": False, "required_values": False,
                "citations": False, "scope": False, "http_status": response.status_code}
    data = response.json()
    expected = set(case["expected"])
    citations = data["citations"]
    answer = data["answer"]
    cited = {identifiers.get(item["chunk_id"]) for item in citations}
    anchors_valid = all(
        anchors.get(item["chunk_id"]) == (item["document_id"], item["page_start"], item["page_end"])
        for item in citations
    )
    return {
        "success_status": True,
        "abstention": bool(data["abstained"]) == (not case["fixture_answer"]),
        "required_values": all(contains_answer_value(answer, fragment) for fragment in case["answer_contains"])
        and not any(contains_answer_value(answer, fragment) for fragment in case.get("answer_excludes", [])),
        "citations": (expected <= cited if expected else not cited) and anchors_valid,
        "scope": all(item["document_id"] in allowed for item in [*data["evidence"], *citations]),
    }


def evaluate(live_provider: bool = False, live_embeddings: bool = False) -> dict:
    fixture = json.loads(CORPUS.read_text(encoding="utf-8"))
    schema = fresh_schema()
    results = []
    # The fresh namespace and all rows disappear with this rollback. The
    # library's tables are never selected, updated, truncated, or recreated.
    with get_connection() as conn, conn.transaction(force_rollback=True):
        prepare_schema(conn, schema)
        docs, identifiers, anchors, workspaces, settings = insert_fixtures(conn, fixture, live_embeddings)

        @contextmanager
        def request_connection():
            with conn.transaction():
                yield conn

        with ExitStack() as bound, TestClient(app) as client:
            bound.enter_context(patch("app.api.main.get_connection", request_connection))
            for retriever in (keyword, vector):
                bound.enter_context(patch.object(retriever, "get_connection", lambda: nullcontext(conn)))
                bound.enter_context(patch.object(retriever, "get_settings", lambda: settings))
            for case in fixture["cases"]:
                ws = workspaces[case["workspace"]]
                allowed = {docs[key] for key in fixture["workspaces"][case["workspace"]]}
                expected = set(case["expected"])
                stages = {}
                with ExitStack() as mode:
                    if not live_embeddings:
                        mode.enter_context(patch.object(vector, "embed_query", lambda _: case["vector"]))
                    if not live_provider:
                        reply = case["fixture_answer"]
                        provider = SimpleNamespace(generate_json=lambda **_: json.dumps({
                            "answer": reply, "abstained": not reply, "reason": None if reply else "Insufficient evidence.",
                        }))
                        mode.enter_context(patch.object(answerer, "get_generation_provider", return_value=provider))
                    for name, search in (("keyword", keyword.search_keyword), ("vector", vector.search_vector),
                                         ("hybrid", fusion.search_hybrid)):
                        started = perf_counter()
                        rows = search(case["query"], top_k=TOP_K, workspace_id=ws)
                        ranking = [identifiers[item["chunk_id"]] for item in rows]
                        stages[name] = {**retrieval_metrics(ranking, expected), "ranked": ranking,
                                        "scope_ok": all(item["document_id"] in allowed for item in rows),
                                        "elapsed_ms": (perf_counter() - started) * 1000}
                    started = perf_counter()
                    response = client.post("/answers", json={"query":case["query"], "workspace_id":ws, "top_k":TOP_K})
                    answer_latency = (perf_counter() - started) * 1000
                checks = answer_checks(response, case, identifiers, anchors, allowed)
                passed = (all(stage["scope_ok"] for stage in stages.values())
                          and (not expected or stages["hybrid"]["recall"] == 1)
                          and all(checks.values()))
                results.append({"id":case["id"], "passed":passed, "retrieval":stages,
                                "answer_checks":checks, "answer_elapsed_ms":answer_latency})

    averages = {}
    for stage in ("keyword", "vector", "hybrid"):
        stats = [case["retrieval"][stage] for case in results]
        averages[stage] = {
            key: round(mean(row[key] for row in stats if row[key] is not None), 3)
            for key in ("precision", "recall", "reciprocal_rank")
        }
        averages[stage].update(latencies([row["elapsed_ms"] for row in stats]))
    return {
        "corpus_version":fixture["version"], "top_k":TOP_K,
        "model_mode":"live" if live_provider else "fixture",
        "embedding_mode":"live" if live_embeddings else "fixture",
        "passed":sum(case["passed"] for case in results), "case_count":len(results),
        "retrieval":averages, "answer_latency":latencies([case["answer_elapsed_ms"] for case in results]),
        "cases":results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Print the full evaluation report as JSON.")
    parser.add_argument("--live-provider", action="store_true", help="Send only synthetic excerpts to the configured provider.")
    parser.add_argument("--live-embeddings", action="store_true", help="Use the configured embedding model instead of fixture vectors.")
    args = parser.parse_args()
    report = evaluate(args.live_provider, args.live_embeddings)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"{report['passed']}/{report['case_count']} cases passed. Corpus v{report['corpus_version']}.")
        for stage, stats in report["retrieval"].items():
            print(f"{stage:7} recall@{TOP_K} {stats['recall']:.3f} · MRR {stats['reciprocal_rank']:.3f} · p95 {stats['p95_ms']:.2f} ms")
        print(f"answer  p95 {report['answer_latency']['p95_ms']:.2f} ms")
        for case in report["cases"]:
            if not case["passed"]:
                print(f"FAIL {case['id']}: {case['answer_checks']}")
    return int(report["passed"] != report["case_count"])


if __name__ == "__main__":
    raise SystemExit(main())
