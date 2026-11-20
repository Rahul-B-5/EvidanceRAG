"""Reusable briefing outlines and evidence requirements."""

import re
from typing import Literal

TemplateID = Literal["general", "literature-review", "technical-comparison", "methodology",
                     "research-gap", "reproduction", "question-investigation"]

TEMPLATES = {
    "general": ("Research briefing", ("Findings", "Limitations", "Unresolved questions"),
                "Separate supported findings from limitations and open questions."),
    "literature-review": (
        "Literature review", ("Scope", "Themes across studies", "Differences and uncertainty", "Open questions"),
        "Group by themes and cite each source. Distinguish a finding in one study from convergence across multiple studies.",
    ),
    "technical-comparison": (
        "Technical comparison", ("Methods and baselines", "Evaluation conditions", "Reported outcomes", "Comparability limits"),
        "Compare only compatible outcomes. Name incompatible or missing conditions before discussing numerical differences.",
    ),
    "methodology": (
        "Methodology overview", ("Study design", "Data and preprocessing", "Implementation and evaluation", "Missing details"),
        "Separate the authors' documented procedures from settings or steps missing from the excerpts.",
    ),
    "research-gap": (
        "Research-gap brief", ("Reported limitations", "Related evaluations", "Candidate research question", "Validation plan"),
        "Name counterexamples when available. Frame the gap as local to the supplied evidence and proposed work as a hypothesis.",
    ),
    "reproduction": (
        "Reproduction dossier", ("Reported setup", "Artifacts and access", "Unspecified requirements", "Verification steps"),
        "Separate reported values, access constraints and unknowns. Label any proposed verification steps as proposals.",
    ),
    "question-investigation": (
        "Question investigation", ("Scope of the question", "Evidence by subquestion", "Provisional answer", "Remaining evidence needs"),
        "Answer supported parts and state which subquestions still lack evidence. Distinguish direct reporting from interpretation.",
    ),
}


def list_templates() -> list[dict]:
    return [{"id": id_, "title": title, "sections": list(sections)} for id_, (title, sections, _) in TEMPLATES.items()]


def draft_instruction(template: TemplateID, question: str) -> str:
    title, sections, guidance = TEMPLATES[template]
    return (
        f"Draft a concise {title.lower()} with these Markdown headings: {', '.join(sections)}. "
        f"{guidance} Cite each substantive observation. If the supplied excerpts omit a detail, say so. "
        f"Research question: {question}"
    )


def unknown_citations(narrative: str, item_count: int) -> list[str]:
    expected = {f"E{index}" for index in range(1, item_count + 1)}
    return list(dict.fromkeys(label for label in re.findall(r"\[(E[0-9]+)\]", narrative) if label not in expected))
