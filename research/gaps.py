"""Surface author-reported limitations and corpus-scoped research directions."""

import re
from collections.abc import Iterator
from dataclasses import dataclass

from app.db.connection import get_connection
from research.structured import normalize


@dataclass(frozen=True)
class GapTheme:
    id: str
    title: str
    query: str
    context: str
    coverage: str
    investigation: str
    validation: str


THEMES = (
    GapTheme("generalization", "Generalization and external validation",
             '"external validation" OR generalization OR generalize OR "single dataset" OR "domain shift" OR "external site" OR "independent cohort"',
             r"\b(?:generaliz\w*|external validation|domain shift|single (?:dataset|site|domain))\b",
             r"\b(?:external validation (?:was )?(?:performed|conducted)|(?:evaluated|tested|validated) on (?:an? )?"
             r"(?:external|independent|out-of-domain|held-out site))\b",
             "How does the approach perform on held-out domains under a fixed training protocol?",
             "Keep the original split as a reference. Evaluate additional sites or domains with disjoint data and report per-domain performance."),
    GapTheme("data", "Data and label coverage",
             '"limited data" OR "small sample" OR annotation OR "class imbalance" OR labeling OR labels OR "label budget" OR agreement',
             r"\b(?:label\w*|annotation\w*|small sample|class imbalance|limited data|data scarcity)\b",
             r"\b(?:annotated by \d+|sampled \d+ (?:records|observations|images)|"
             r"evaluated across \d+ (?:label budgets|class distributions)|measured inter[- ]annotator agreement)\b",
             "How does performance change as the annotation budget and class coverage vary?",
             "Compare the same train/test split across several label budgets and seeds. Report per-class results and class prevalence."),
    GapTheme("robustness", "Robustness and stress testing",
             'robustness OR corruption OR perturbation OR noise OR occlusion OR "distribution shift"',
             r"\b(?:robustness|corruption\w*|perturbation\w*|noise|occlusion|distribution shift)\b",
             r"\b(?:evaluated|tested|validated) (?:robustness )?(?:under|against|with) "
             r"(?:\d+ (?:levels of )?)?(?:corruptions?|perturbations?|noise|occlusion|distribution shift)\b",
             "Which controlled changes in inputs most affect the reported method?",
             "Predefine clean and stressed conditions, keep evaluation examples paired, and report uncertainty at each stress level."),
    GapTheme("compute", "Compute and deployment constraints",
             'latency OR "computational cost" OR compute OR hardware OR inference OR runtime OR "peak memory"',
             r"\b(?:latency|computational cost|compute|memory|inference time|hardware)\b",
             r"\b(?:latency|inference time|peak memory) (?:of|was|measured at) \d|"
             r"\b(?:measured|profiled) (?:inference )?(?:latency|runtime|peak memory)\b",
             "How does predictive performance trade off against runtime and memory under a common workload?",
             "Profile methods on the same hardware, precision and batch sizes. Measure wall time and peak memory alongside the original metric."),
    GapTheme("evaluation", "Missing evaluation or baselines",
             'baseline OR ablation OR evaluation OR comparison OR benchmark',
             r"\b(?:baselines?|ablation\w*|comparison|compared|evaluation|benchmark)\b",
             r"\b(?:conducted|performed|ran) (?:an? )?ablations?\b|\bcompared (?:our |the )?\w+ "
             r"(?:to|against|with) (?:\d+ |the )?baselines?\b",
             "Does the claimed improvement persist against stronger baselines and controlled ablations?",
             "Match data, preprocessing, tuning budget and metric across methods. Remove one component at a time and report paired uncertainty."),
)

QUALIFIER = re.compile(
    r"\b(?:limitations?|limited to|future (?:work|research|studies)|further (?:work|research|investigation|evaluation)|"
    r"remains? (?:unclear|unexplored|an open question)|(?:we|this study) (?:did not|could not|only)|"
    r"has not been (?:tested|evaluated|explored))\b",
    re.IGNORECASE,
)
HEDGE = re.compile(r"\b(?:not|never|might|may|could|would|plan to|will|proposed)\b", re.IGNORECASE)


def topic_sentences(text: str, focus: frozenset[str]) -> Iterator[str]:
    for sentence in re.split(r"(?<=[.!?])\s+", normalize(text)):
        if not focus or focus <= set(re.findall(r"[\w-]+", sentence.casefold())):
            yield sentence


def qualifying_excerpt(text: str, context: str, focus: frozenset[str] = frozenset()) -> tuple[str, str] | None:
    subject = re.compile(context, re.IGNORECASE)
    for sentence in topic_sentences(text, focus):
        for qualifier in QUALIFIER.finditer(sentence):
            start, end = max(0, qualifier.start() - 120), qualifier.end() + 180
            if subject.search(sentence, start, end):
                return sentence[start:end].strip(), qualifier.group(0)
    return None


def coverage_excerpt(text: str, pattern: str, focus: frozenset[str] = frozenset()) -> tuple[str, str] | None:
    for sentence in topic_sentences(text, focus):
        if HEDGE.search(sentence) or QUALIFIER.search(sentence):
            continue
        match = re.search(pattern, sentence, re.IGNORECASE)
        if match:
            head = max(0, match.start() - 140)
            tail = min(len(sentence), match.end() + 170)
            return sentence[head:tail].strip(), match.group(0)
    return None


def sampled_passages(query: str, focus: str, workspace_id: int | None) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute("""
            WITH terms AS (
                SELECT websearch_to_tsquery('english', %s) AS theme,
                       plainto_tsquery('english', %s) AS focus
            ), matches AS (
                SELECT c.id, c.document_id, d.title, c.page_start, c.page_end, c.text,
                       ts_rank_cd(c.search_vector, q.theme) AS score
                FROM chunks c JOIN documents d ON d.id = c.document_id CROSS JOIN terms q
                WHERE c.search_vector @@ q.theme
                  AND (%s = '' OR c.search_vector @@ q.focus)
                  AND (%s::bigint IS NULL OR EXISTS (
                      SELECT 1 FROM workspace_documents m
                      WHERE m.workspace_id = %s AND m.document_id = c.document_id
                  ))
            ), ranked AS (
                SELECT *, row_number() OVER (PARTITION BY document_id ORDER BY score DESC, id) AS paper_rank
                FROM matches
            )
            SELECT id, document_id, title, page_start, page_end, text FROM ranked
            WHERE paper_rank <= 3 ORDER BY paper_rank, score DESC, id LIMIT 96
        """, (query, focus, focus, workspace_id, workspace_id)).fetchall()
    fields = ("chunk_id", "document_id", "title", "page_start", "page_end", "text")
    return [dict(zip(fields, row, strict=True)) for row in rows]


def research_directions(workspace_id: int | None, focus: str = "") -> dict:
    directions = []
    reviewed: set[int] = set()
    coverage_only = []
    focus_terms = frozenset(re.findall(r"[\w-]+", focus.casefold()))

    for theme in THEMES:
        sources = {}
        examples = {}
        theme_reviewed = set()
        for passage in sampled_passages(theme.query, focus, workspace_id):
            id_ = passage["document_id"]
            theme_reviewed.add(id_)
            provenance = {key: value for key, value in passage.items() if key != "text"}
            if id_ not in sources and (match := qualifying_excerpt(passage["text"], theme.context, focus_terms)):
                sources[id_] = {**provenance, "excerpt": match[0], "signal": match[1]}
            if id_ not in examples and (match := coverage_excerpt(passage["text"], theme.coverage, focus_terms)):
                examples[id_] = {**provenance, "excerpt": match[0], "signal": match[1]}
        reviewed.update(theme_reviewed)
        if sources:
            directions.append({
                "id": theme.id, "title": theme.title, "evidence": list(sources.values())[:8],
                "paper_count": len(sources), "reviewed_paper_count": len(theme_reviewed),
                "coverage_paper_count": len(examples), "coverage": list(examples.values())[:8],
                "verification": "requires_broader_verification",
                "plan": {
                    "question": theme.investigation,
                    "hypothesis": "",
                    "baseline": "Reproduce the source study's reference method before testing changes.",
                    "metrics": "Use the source study's primary metric and report uncertainty across independent runs.",
                    "validation": theme.validation,
                },
            })
        elif examples:
            coverage_only.append({"id": theme.id, "title": theme.title, "paper_count": len(examples),
                                  "evidence": list(examples.values())[:4]})
    directions.sort(key=lambda d: (-d["paper_count"], d["title"]))
    return {"directions": directions, "reviewed_paper_count": len(reviewed), "coverage_only": coverage_only}
