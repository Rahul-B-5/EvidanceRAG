"""Identify explicitly opposing source statements under matching reported conditions."""

import re
from collections import defaultdict
from itertools import combinations
from psycopg import Connection

CONDITIONS = ("metric", "dataset", "task", "split", "protocol", "baseline")
REQUIRED_FIELDS = ("subject", *CONDITIONS)
COMPARISON_VERBS = "outperformed|underperformed|performed better than|performed worse than"
NAMED_ITEM = r"[\w-]+(?:[./][\w-]+)*"
EXPLICIT_SETUP = re.compile(
    rf"\b(?:For|In) (?P<task>[\w-]+(?: [\w-]+){{0,5}}) on (?:the )?"
    rf"(?P<dataset>{NAMED_ITEM})(?: dataset| benchmark)? "
    rf"(?:using|with|under) (?:the )?(?P<split>[\w-]+(?: [\w-]+){{0,5}} split) and (?:the )?"
    rf"(?P<protocol>[\w-]+(?: [\w-]+){{0,5}} protocol), "
    rf"(?P<subject>{NAMED_ITEM}) (?:significantly )?(?:{COMPARISON_VERBS}) "
    rf"(?P<baseline>{NAMED_ITEM}) (?:on|in) (?P<metric>{NAMED_ITEM}(?:[- ]score)?)(?=[.?!]|$)",
    re.IGNORECASE,
)
QUALIFIED = re.compile(
    r"\b(?:not|cannot|no|never|neither|nor|only if|might|may|could|would|hypothes\w*|"
    r"expected|predicted|assumed|simulated outcome|previous work|prior work|previously|according to)\b", re.IGNORECASE,
)


def exact_in(fragment: str, text: str) -> bool:
    return bool(re.search(r"(?<![\w-])" + re.escape(fragment) + r"(?![\w-])", text))


def relative_statement(quote: str, reported: dict) -> dict | None:
    """Require the subject, comparator and every reported condition in one statement."""
    if any(not reported.get(field) for field in REQUIRED_FIELDS):
        return None
    conditions = {field: reported[field] for field in REQUIRED_FIELDS}
    if conditions["subject"].casefold() == conditions["baseline"].casefold():
        return None
    subject, baseline = (re.escape(conditions[field]) for field in ("subject", "baseline"))
    grammatical_pair = re.compile(
        rf"(?<![\w-]){subject}\s+(?:significantly\s+)?"
        rf"(?P<relation>{COMPARISON_VERBS})\s+"
        rf"{baseline}(?=[.!?;,:]|\s+(?:on|in|by|for|with|under|using)\b|$)",
        re.IGNORECASE,
    )
    statements = []
    for sentence in re.split(r"(?<=[.!?])\s+", quote):
        if QUALIFIED.search(sentence) or not all(exact_in(value, sentence) for value in conditions.values()):
            continue
        relations = list(grammatical_pair.finditer(sentence))
        if len(relations) != 1:
            continue
        relation = relations[0]["relation"].casefold()
        direction = "better" if relation in {"outperformed", "performed better than"} else "worse"
        statements.append({"quote": sentence, "direction": direction, "conditions": conditions})
    return statements[0] if len(statements) == 1 else None


def recover_relative_statement(quote: str) -> dict | None:
    """Copy labels from a directly stated, self-contained comparison clause."""
    matches = list(EXPLICIT_SETUP.finditer(quote))
    if len(matches) != 1:
        return None
    return relative_statement(quote, matches[0].groupdict())


def opposing_statements(papers: list[dict], conn: Connection | None = None) -> list[dict]:
    grouped: dict[tuple[str, ...], dict[int, dict[str, dict]]] = defaultdict(lambda: defaultdict(dict))
    for paper in papers:
        for finding in paper["findings"]:
            statement = finding.get("relative_statement")
            if finding["topic"] != "results" or not statement or finding["source"]["document_id"] != paper["document_id"]:
                continue
            verified = relative_statement(finding["quote"], statement["conditions"])
            if verified != statement:
                continue
            labels = tuple(statement["conditions"][key].casefold() for key in REQUIRED_FIELDS)
            grouped[labels][paper["document_id"]].setdefault(statement["direction"], {
                "title": paper["title"], "source": finding["source"],
                "quote": statement["quote"], "direction": statement["direction"],
                "finding_quote": finding["quote"],
                "conditions": statement["conditions"],
            })

    result = []
    for paper_statements in grouped.values():
        # Mixed directions within one paper need manual disambiguation.
        candidates = [next(iter(items.values())) for items in paper_statements.values() if len(items) == 1]
        for left, right in combinations(candidates, 2):
            if left["direction"] == right["direction"]:
                continue
            # All items in this group share the case-folded labels. Keep the
            # spelling of the supporting source in the displayed labels.
            pair = {"left": {k: v for k, v in left.items() if k != "conditions"},
                    "right": {k: v for k, v in right.items() if k != "conditions"},
                    "conditions": left["conditions"]}
            result.append(pair)
            if len(result) == 36:
                return current_sources(result, conn) if conn is not None else result
    return current_sources(result, conn) if conn is not None else result


def current_sources(pairs: list[dict], conn: Connection) -> list[dict]:
    if not pairs:
        return pairs
    chunk_ids = {pair[side]["source"]["chunk_id"] for pair in pairs for side in ("left", "right")}
    rows = conn.execute("""
        SELECT id, document_id, page_start, page_end, text FROM chunks
        WHERE id = ANY(%s::bigint[])
    """, (sorted(chunk_ids),)).fetchall()
    passages = {id_: (paper, start, end, " ".join(text.split())) for id_, paper, start, end, text in rows}

    def still_indexed(statement: dict) -> bool:
        source = statement["source"]
        passage = passages.get(source["chunk_id"])
        return (passage is not None
                and (source["document_id"], source["page_start"], source["page_end"]) == passage[:3]
                and statement["finding_quote"] in passage[3])

    return [pair for pair in pairs if still_indexed(pair["left"]) and still_indexed(pair["right"])]
