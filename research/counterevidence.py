"""Find scoped passages that may qualify a persisted comparison excerpt."""

import re
from collections import Counter

from app.db.connection import get_connection
from research.structured import CONDITIONS, normalize

CHALLENGE = re.compile(
    r"\b(?:no significant (?:difference|effect|improvement)|did not (?:improve|outperform|generalize)|"
    r"failed to (?:improve|outperform|generalize)|contrary to|underperformed|degraded|"
    r"lower than|worse than|limitation(?:s)?|does not generalize)\b",
    re.IGNORECASE,
)
STOP_WORDS = frozenset("""
about above across after again also approach based before between both can could data does each
from have into method more most only our paper results study than their them then these this
those through used using very well were when where which while will with would and the for
that shown model models between evaluated system evaluation performance showed compared
""".split())


def focus_terms(finding: dict) -> list[str]:
    context = " ".join(str(value) for key, value in finding.get("outcome", {}).items() if key in CONDITIONS)
    tokens = Counter(re.findall(r"[a-z][a-z0-9-]{2,40}", finding["label"].lower()))
    for word in re.findall(r"[a-z][a-z0-9-]{1,40}", context.lower()):
        tokens[word] += 3
    return [word for word, _ in tokens.most_common() if word not in STOP_WORDS][:12]


def rank_passages(rows: list, finding: dict, terms: list[str], limit: int = 8) -> list[dict]:
    result = []
    for chunk, document, title, start, end, text, score in rows:
        if document == finding["provenance"]["document_id"]:
            continue
        text = normalize(text)
        lower = text.lower()
        matched = [term for term in terms if re.search(r"\b" + re.escape(term) + r"\b", lower)]
        if not matched:
            continue
        terms_regex = re.compile(r"\b(?:" + "|".join(map(re.escape, matched)) + r")\b", re.IGNORECASE)
        cue = next((cue for cue in CHALLENGE.finditer(text)
                    if terms_regex.search(text[max(0, cue.start() - 120):cue.end() + 120])), None)
        pivot = cue.start() if cue else terms_regex.search(text).start()
        excerpt = text[max(0, pivot - 180):pivot + 260].strip()
        labels = {
            condition: value for condition, value in finding.get("outcome", {}).items()
            if condition in CONDITIONS and re.search(r"(?<!\w)" + re.escape(value) + r"(?!\w)", excerpt, re.IGNORECASE)
        }
        result.append({
            "chunk_id": chunk, "document_id": document, "title": title,
            "page_start": start, "page_end": end, "excerpt": excerpt,
            "signal": cue.group(0) if cue else None,
            "matched_terms": matched, "condition_labels": labels,
            "_rank": (len(labels), bool(cue), len(matched), score, -chunk),
        })
    result.sort(key=lambda item: item["_rank"], reverse=True)
    return [{k: v for k, v in item.items() if k != "_rank"} for item in result[:limit]]


def find_passages(finding: dict, workspace_id: int | None) -> list[dict]:
    terms = focus_terms(finding)
    if not terms:
        return []
    # These terms were extracted from a bounded alphabet and are parameterized.
    # SQL excludes the originating paper before candidate ranking and limiting.
    query = " OR ".join(f'"{word}"' for word in terms)
    with get_connection() as conn:
        rows = conn.execute("""
            WITH q AS (SELECT websearch_to_tsquery('english', %s) AS tsq)
            SELECT c.id, c.document_id, d.title, c.page_start, c.page_end, c.text,
                   ts_rank_cd(c.search_vector, q.tsq) AS rank
            FROM chunks c JOIN documents d ON d.id=c.document_id CROSS JOIN q
            WHERE c.document_id<>%s AND c.search_vector @@ q.tsq
                AND (%s::bigint IS NULL OR EXISTS (
                    SELECT 1 FROM workspace_documents m WHERE m.document_id=c.document_id AND m.workspace_id=%s
                ))
            ORDER BY rank DESC, c.id LIMIT 60
        """, (query, finding["provenance"]["document_id"], workspace_id, workspace_id)).fetchall()
    return rank_passages(rows, finding, terms)
