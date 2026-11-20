"""Exercise the complete import and answer workflow on a pinned public NREL report."""
import argparse
import importlib
import json
import os
import re
from contextlib import ExitStack
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import psycopg
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.ingestion import jobs, pipeline
from app.retrieval import keyword, vector
from evaluation.database import isolated_database
from evaluation.run import contains_answer_value

api = importlib.import_module("app.api.main")
REPORT_URL = "https://www.osti.gov/servlets/purl/2005540"
REPORT_SHA256 = "d215db18c284cf154345d8c9b267639cebde8efc9debfd5df1300ed9b8885b45"
TOP_K = 12
# Physical PDF pages. The report itself also uses Roman numerals and printed pages.
CASES = (
    ("residential-market-price",
     "What was the Q1 2023 modeled market price (MMP) for the 8-kWdc residential rooftop PV system "
     "without storage, in dollars per watt DC? Attach the source citation to the price.",
     {"2.68": (7, 30, 45)}, ()),
    ("community-market-and-sustainable-prices",
     "What were the Q1 2023 modeled market price (MMP) and minimum sustainable price (MSP) for "
     "the fixed-tilt 3-MWdc community solar system without storage, in dollars per watt DC? Cite both.",
     {"1.76": (7, 34, 45), "1.49": (7, 34, 45)}, ("2.94", "2.33")),
    ("disagreement-within-the-report",
     "Compare the Q1 2023 modeled market price (MMP) of the 100-MWdc one-axis-tracking utility-scale PV "
     "system without storage in the Executive Summary and Table 3. Give each section's reported price, "
     "including any inconsistency, with a separate source citation for each number.",
     {"1.16": (7,), "1.17": (45,)}, ("0.96", "0.97", "2.11", "2.13")),
    ("no-local-installer-quote",
     "What price in dollars per watt DC did a named Boise, Idaho installer quote an individual homeowner "
     "in February 2023? Answer only if the source gives the actual site-specific quote.",
     {}, ()),
)


def supported_fact(passages: list[dict], value: str, pages: tuple[int, ...]) -> bool:
    return any(item["page_start"] in pages and item["page_start"] == item["page_end"]
               and contains_answer_value(item["text"], value) for item in passages)


def check_answer(payload: dict, facts: dict[str, tuple[int, ...]], excludes: tuple[str, ...], paper: int) -> dict:
    evidence = {item["evidence_id"]: item for item in payload["evidence"]}
    citations = {item["evidence_id"]: item for item in payload["citations"]}
    answer = payload["answer"]
    statements = re.split(r"(?<=[.!?])\s+(?!\[E\d+\])|\n+", answer)
    return {
        "abstention": payload["abstained"] == (not facts),
        "source_anchors": all(
            tag in evidence and item["document_id"] == paper and
            all(item.get(key) == evidence[tag].get(key)
                for key in ("chunk_id", "page_start", "page_end", "section_title"))
            for tag, item in citations.items()
        ),
        "cited_facts": all(
            any(contains_answer_value(statement, value) and
                supported_fact([evidence[tag] for tag in re.findall(r"\[(E\d+)\]", statement)
                                if tag in citations and tag in evidence], value, pages)
                for statement in statements)
            for value, pages in facts.items()
        ) and (bool(citations) == bool(facts)),
        "excludes_other_results": not any(contains_answer_value(answer, value) for value in excludes),
    }


def check_report_disagreement(payload: dict) -> bool:
    cited = {item["evidence_id"] for item in payload["citations"]}
    for source in payload["evidence"]:
        row = source.get("table_row") or {}
        if source["evidence_id"] not in cited or source["page_start"] != 45:
            continue
        if (row.get("caption", "").startswith("Table 3.")
                and row.get("group") == "Utility-Scale Systems"
                and any(cell["column"] == "MMP Benchmarks" and cell["value"].replace(" ", "") == "$1.17/Wdc"
                        for cell in row["cells"])
                and any("one-axis-tracking PV system cost" in cell["value"] for cell in row["cells"])):
            return any(item["page_start"] == 7 and item.get("section_title") == "Executive Summary"
                       for item in payload["citations"])
    return False


def evaluate_pdf(path: Path, *, retrieval_only: bool = False) -> dict:
    source_bytes = path.read_bytes()
    if sha256(source_bytes).hexdigest() != REPORT_SHA256:
        raise ValueError(f"Select the pinned public report from {REPORT_URL}.")
    with isolated_database() as (_, dsn), TemporaryDirectory(prefix="evidencerag-pdf-eval-") as uploads, ExitStack() as bound:
        settings = get_settings().model_copy(update={"upload_dir": Path(uploads)})
        for module in (api, jobs, pipeline, keyword, vector):
            bound.enter_context(patch.object(module, "get_connection", lambda: psycopg.connect(dsn)))
        bound.enter_context(patch("app.generation.profile_store.get_connection", lambda: psycopg.connect(dsn)))
        for module in (api, jobs, pipeline):
            bound.enter_context(patch.object(module, "get_settings", lambda: settings))

        client = TestClient(api.app, base_url="http://127.0.0.1")
        upload = client.post("/import-jobs", files={"file": ("nrel-87303.pdf", source_bytes, "application/pdf")})
        upload.raise_for_status()
        if not jobs.process_next_job():
            raise RuntimeError("The public PDF import did not run.")
        job = client.get("/import-jobs").json()["jobs"][0]
        if job["state"] != "imported":
            raise RuntimeError(f"The public PDF import failed. {job['error']}")
        paper = job["document_id"]
        original = client.get(f"/documents/{paper}/source")
        original.raise_for_status()
        details = client.get(f"/documents/{paper}").json()

        results = []
        for name, question, facts, excludes in CASES:
            if retrieval_only and not facts:
                continue
            params = {"query": question, "document_id": paper, "top_k": TOP_K}
            response = client.get("/search", params=params) if retrieval_only else client.post("/answers", json=params)
            if response.status_code != 200:
                results.append({"case": name, "passed": False, "error": response.json().get("detail")})
                continue
            data = response.json()
            checks = {"retrieved_facts": all(supported_fact(data["evidence"], value, pages) for value, pages in facts.items())}
            if not retrieval_only:
                checks.update(check_answer(data, facts, excludes, paper))
                if name == "disagreement-within-the-report":
                    checks["distinct_section_and_exact_table_row"] = check_report_disagreement(data)
            results.append({"case": name, "passed": all(checks.values()), "checks": checks,
                            "retrieved_pages": sorted({item["page_start"] for item in data["evidence"]}),
                            "citations": data.get("citations", []),
                            "answer": data.get("answer"), "reason": data.get("reason")})
        return {"source": REPORT_URL, "source_identical": sha256(original.content).hexdigest() == REPORT_SHA256,
                "pages": details["page_count"], "passages": details["chunk_count"], "top_k": TOP_K, "cases": results}


def main() -> int:
    os.environ.setdefault("PYMUPDF_SUGGEST_LAYOUT_ANALYZER", "0")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--retrieval-only", action="store_true", help="Use the configured embedding model without generating answers.")
    args = parser.parse_args()
    report = evaluate_pdf(args.pdf, retrieval_only=args.retrieval_only)
    print(json.dumps(report, indent=2))
    return int(not report["source_identical"] or not all(case["passed"] for case in report["cases"]))


if __name__ == "__main__":
    raise SystemExit(main())
