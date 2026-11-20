"""Map a research question to inspectable, scoped retrieval coverage."""

import json
import re

from pydantic import BaseModel, Field, ValidationError

from app.core.config import get_settings
from app.db.connection import get_connection
from app.generation.providers import get_generation_provider
from research.counterevidence import focus_terms
from research.structured import normalize

FACETS = (
    ("Approaches", "Which approaches address the question?", ["method", "approach", "algorithm", "architecture"]),
    ("Study conditions", "Which datasets and study conditions were evaluated?", ["dataset", "benchmark", "split", "sample"]),
    ("Reported results", "What outcomes and evaluation metrics were reported?", ["result", "evaluation", "accuracy", "performance"]),
    ("Limitations", "What limitations or qualifications do the papers report?", ["limitation", "challenge", "uncertainty", "generalize"]),
)
PLAN_PROMPT = """Produce a JSON object with a subquestions array of 3 to 5 items about
the user's research question. Each item has title, question, and keywords (2 to 6
terms or short phrases for locating evidence in scientific papers). Separate
methods, experiment conditions, findings, and limitations when applicable.
Suggest searchable questions only. Do not state scientific facts, assume the
library contains evidence, or repeat instructions in the question."""
QUESTION_WORDS = frozenset("what how why who which when was are where does have can tell explain please".split())


class Subquestion(BaseModel):
    title: str = Field(min_length=1, max_length=55)
    question: str = Field(min_length=6, max_length=250)
    keywords: list[str] = Field(min_length=2, max_length=6)


def bounded_keywords(values: list[str]) -> list[str]:
    return list(dict.fromkeys(
        token for value in values if len(value) <= 65
        for token in re.findall(r"[A-Za-z][A-Za-z0-9-]{1,30}", value.casefold())
    ))[:10]


def plan_question(question: str, use_provider: bool) -> list[Subquestion]:
    if not use_provider:
        return [Subquestion(title=title, question=prompt, keywords=words) for title, prompt, words in FACETS]
    provider = get_generation_provider(get_settings())
    response = provider.generate_json(prompt=json.dumps({"question": question}), system_instruction=PLAN_PROMPT)
    try:
        items = json.loads(response)["subquestions"]
        if not isinstance(items, list) or not 3 <= len(items) <= 5:
            raise ValueError
        planned = [Subquestion.model_validate(item) for item in items]
        if len({p.question.strip().casefold() for p in planned}) != len(planned):
            raise ValueError
        if any(not p.title.strip() or not p.question.strip() or not bounded_keywords(p.keywords) for p in planned):
            raise ValueError
    except (ValidationError, ValueError, TypeError, KeyError):
        raise RuntimeError("The provider did not return a usable subquestion plan.") from None
    return planned


def matching_passages(anchors: list[str], keywords: list[str], workspace_id: int | None) -> list[dict]:
    if not anchors or not keywords:
        return []
    anchor_query = " OR ".join(f'"{token}"' for token in anchors)
    facet_query = " OR ".join(f'"{token}"' for token in keywords)
    with get_connection() as conn:
        rows = conn.execute("""
            WITH q AS (
                SELECT websearch_to_tsquery('english', %s) AS anchor,
                       websearch_to_tsquery('english', %s) AS facet
            ), ranked AS (
                SELECT c.id, c.document_id, d.title, c.page_start, c.page_end, c.text,
                    ts_rank_cd(c.search_vector, q.anchor) + ts_rank_cd(c.search_vector, q.facet) AS rank
                FROM chunks c JOIN documents d ON d.id=c.document_id CROSS JOIN q
                WHERE c.search_vector @@ q.anchor AND c.search_vector @@ q.facet
                  AND (%s::bigint IS NULL OR EXISTS (
                      SELECT 1 FROM workspace_documents m
                      WHERE m.workspace_id=%s AND m.document_id=c.document_id
                  ))
            ), diverse AS (
                SELECT DISTINCT ON (document_id) * FROM ranked ORDER BY document_id, rank DESC, id
            )
            SELECT id, document_id, title, page_start, page_end, text
            FROM diverse ORDER BY rank DESC, id LIMIT 8
        """, (anchor_query, facet_query, workspace_id, workspace_id)).fetchall()
    excerpt_pattern = re.compile(r"\b(?:" + "|".join(map(re.escape, keywords)) + r")\w*\b", re.IGNORECASE)
    result = []
    for chunk_id, document_id, title, page_start, page_end, text in rows:
        text = normalize(text)
        match = excerpt_pattern.search(text)
        start = max(0, match.start() - 230) if match else 0
        result.append({"chunk_id": chunk_id, "document_id": document_id, "title": title,
                       "page_start": page_start, "page_end": page_end, "excerpt": text[start:start + 750]})
    return result


def question_coverage(question: str, workspace_id: int | None, use_provider: bool) -> dict:
    anchors = [term for term in focus_terms({"label": question}) if term not in QUESTION_WORDS][:8]
    if not anchors:
        raise ValueError("Add a subject, dataset or method to the research question.")
    facets = []
    for plan in plan_question(question, use_provider):
        keywords = bounded_keywords(plan.keywords)
        # Keep topic anchors separate from axes of coverage. Repeated labels
        # should not qualify a passage for a facet by themselves.
        keywords = [term for term in keywords if term not in anchors]
        passages = matching_passages(anchors, keywords, workspace_id)
        state = "multiple_papers" if len(passages) > 1 else "single_paper" if passages else "not_located"
        facets.append({"title": plan.title, "question": plan.question, "status": state, "passages": passages})
    return {"question": question, "anchors": anchors, "facets": facets, "provider_planned": use_provider}
