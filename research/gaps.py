"""Surface author-reported limitations and corpus-scoped research directions."""

import re
from dataclasses import dataclass

from app.retrieval.keyword import search_keyword
from research.structured import normalize


@dataclass(frozen=True)
class GapTheme:
    id: str
    title: str
    query: str
    context: str
    investigation: str
    validation: str


THEMES = (
    GapTheme("generalization", "Generalization and external validation",
             '"external validation" OR generalization OR generalize OR "single dataset" OR "domain shift"',
             r"\b(?:generaliz\w*|external validation|domain shift|single (?:dataset|site|domain))\b",
             "How does the approach perform on held-out domains under a fixed training protocol?",
             "Keep the original split as a reference. Evaluate additional sites or domains with disjoint data and report per-domain performance."),
    GapTheme("data", "Data and label coverage",
             '"limited data" OR "small sample" OR annotation OR "class imbalance" OR labeling OR labels',
             r"\b(?:label\w*|annotation\w*|small sample|class imbalance|limited data|data scarcity)\b",
             "How does performance change as the annotation budget and class coverage vary?",
             "Compare the same train/test split across several label budgets and seeds. Report per-class results and class prevalence."),
    GapTheme("robustness", "Robustness and stress testing",
             'robustness OR corruption OR perturbation OR noise OR occlusion OR "distribution shift"',
             r"\b(?:robustness|corruption\w*|perturbation\w*|noise|occlusion|distribution shift)\b",
             "Which controlled changes in inputs most affect the reported method?",
             "Predefine clean and stressed conditions, keep evaluation examples paired, and report uncertainty at each stress level."),
    GapTheme("compute", "Compute and deployment constraints",
             'latency OR "computational cost" OR compute OR hardware OR inference',
             r"\b(?:latency|computational cost|compute|memory|inference time|hardware)\b",
             "How does predictive performance trade off against runtime and memory under a common workload?",
             "Profile methods on the same hardware, precision and batch sizes. Measure wall time and peak memory alongside the original metric."),
    GapTheme("evaluation", "Missing evaluation or baselines",
             'baseline OR ablation OR evaluation OR comparison OR benchmark',
             r"\b(?:baselines?|ablation\w*|comparison|compared|evaluation|benchmark)\b",
             "Does the claimed improvement persist against stronger baselines and controlled ablations?",
             "Match data, preprocessing, tuning budget and metric across methods. Remove one component at a time and report paired uncertainty."),
)

QUALIFIER = re.compile(
    r"\b(?:limitations?|limited to|future (?:work|research|studies)|further (?:work|research|investigation|evaluation)|"
    r"remains? (?:unclear|unexplored|an open question)|(?:we|this study) (?:did not|could not|only)|"
    r"has not been (?:tested|evaluated|explored))\b",
    re.IGNORECASE,
)


def qualifying_excerpt(text: str, context: str) -> tuple[str, str] | None:
    text = normalize(text)
    subject = re.compile(context, re.IGNORECASE)
    for qualifier in QUALIFIER.finditer(text):
        start, end = max(0, qualifier.start() - 120), qualifier.end() + 180
        if subject.search(text, start, end):
            return text[start:end].strip(), qualifier.group(0)
    return None


def research_directions(workspace_id: int | None) -> dict:
    directions = []
    reviewed = set()
    for theme in THEMES:
        sources = {}
        for passage in search_keyword(theme.query, top_k=24, workspace_id=workspace_id):
            id_ = passage["document_id"]
            reviewed.add(id_)
            if id_ in sources:
                continue
            match = qualifying_excerpt(passage["text"], theme.context)
            if match:
                excerpt, signal = match
                sources[id_] = {
                    **{key: passage[key] for key in ("document_id", "chunk_id", "page_start", "page_end", "title")},
                    "excerpt": excerpt, "signal": signal,
                }
        if sources:
            directions.append({
                "id": theme.id, "title": theme.title, "evidence": list(sources.values())[:8],
                "paper_count": len(sources), "verification": "requires_broader_verification",
                "plan": {
                    "question": theme.investigation,
                    "hypothesis": "",
                    "baseline": "Reproduce the source study's reference method before testing changes.",
                    "metrics": "Use the source study's primary metric and report uncertainty across independent runs.",
                    "validation": theme.validation,
                },
            })
    directions.sort(key=lambda d: (-d["paper_count"], d["title"]))
    return {"directions": directions, "reviewed_paper_count": len(reviewed)}
