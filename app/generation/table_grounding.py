"""Conservative grounding for explicit named-table questions with exclusions."""

import re
from dataclasses import dataclass

TABLE = re.compile(r"\btable\s+(?:[a-z][.-]?)?\d+\b", re.I)
EXCLUSION = re.compile(r"\bwithout\s+([\w-]+(?:\s+[\w-]+){0,3}?)(?=\s+(?:in|from|according|as|and|or|at)\b|[.,;?]|$)", re.I)
MEASURE = re.compile(
    r"[-+]?\s*(?:[$€£]\s*)?\d+(?:[,.]\d+)*"
    r"(?:\s*%|\s*/?\s*[°µA-Za-z]{1,6}(?:\s*[/·]\s*[µA-Za-z]{1,6}|\s+[A-Za-z]{1,3}){0,3})?"
)
STANDALONE_NUMBER = re.compile(r"(?<![\w.])[-+]?\d+(?:\.\d+)?(?![\w.])")


def words(text: str) -> list[str]:
    return re.findall(r"[^\W_]+", text.casefold())


def mentions(text: list[str], phrase: list[str]) -> bool:
    return bool(phrase) and any(text[i:i + len(phrase)] == phrase for i in range(len(text)))


def compact(text: str) -> str:
    return re.sub(r"\s+", "", text)


def measurement(value: str) -> bool:
    return bool(MEASURE.fullmatch(value.strip()))


def establishes_exclusion(label: str, siblings: list[tuple[str, dict]], condition: list[str]) -> bool:
    tokens = words(label)
    if mentions(tokens, ["without", *condition]):
        return True
    if any(term in tokens for term in ("with", "plus", "including", "without")):
        return False
    # Some tables name a baseline and an augmented variant. Require a
    # companion row with the same baseline prefix and the explicit addition,
    # including abbreviations only when defined in the same document.
    for sibling, definitions in siblings:
        variant = words(sibling)
        for addition in ("with", "plus", "including"):
            if addition not in variant:
                continue
            boundary = variant.index(addition)
            if boundary < 2 or tokens[:boundary] != variant[:boundary]:
                continue
            addition_tokens = variant[boundary + 1:]
            expanded = [word for token in addition_tokens
                        for word in words(definitions.get(token.upper(), token))]
            if mentions(expanded, condition):
                return True
    return False


@dataclass
class TableScope:
    sources: list[dict]
    table_values: dict[str, list[str]]
    sections: dict[str, set[str]]

    def supports(self, answer: str) -> bool:
        seen = set()
        for statement in re.split(r"(?<=[.!?])\s+(?!\[E\d+\])|\n+", answer):
            anchors = set(re.findall(r"\[(E\d+)\]", statement))
            results = re.sub(r"\[E\d+\]", "", statement)
            source_values = [value for anchor in anchors for value in self.table_values.get(anchor, [])]
            if source_values:
                # Measurements must include the cell's unit and any currency
                # symbol. Compare verbatim except for PDF whitespace.
                remaining = TABLE.sub("", results)
                required = {compact(value) for value in source_values}
                for value in sorted(source_values, key=len, reverse=True):
                    matches = list(re.finditer(
                        r"(?<![\w.])" + r"\s*".join(map(re.escape, compact(value))) + r"(?!\w|\.\d)",
                        remaining,
                    ))
                    for match in reversed(matches):
                        remaining = remaining[:match.start()] + " " + remaining[match.end():]
                    if matches:
                        required.discard(compact(value))
                residue = STANDALONE_NUMBER.findall(remaining)
                if required or residue:
                    return False
                seen.update(anchors.intersection(self.table_values))
            else:
                numbers = STANDALONE_NUMBER.findall(TABLE.sub("", results))
                if not numbers:
                    continue
                supported = {
                    source["evidence_id"] for source in self.sources
                    if source["evidence_id"] in anchors and all(
                        re.search(r"(?<![\d.])" + re.escape(value) + r"(?!\d|\.\d)", source["text"])
                        for value in numbers
                    )
                }
                if not supported:
                    return False
                seen.update(supported)
        return (bool(seen.intersection(self.table_values))
                and all(seen.intersection(ids) for ids in self.sections.values()))


def scope_table_answer(question: str, evidence: list[dict]) -> TableScope | None:
    table_names = {compact(match.group()).casefold() for match in TABLE.finditer(question)}
    excludes = list(EXCLUSION.finditer(question))
    if len(table_names) != 1 or len(excludes) != 1:
        return None
    query = words(question)
    condition = words(excludes[0][1])
    if mentions(query, ["with", *condition]):
        return None
    name = next(iter(table_names))
    tables = []
    sections: dict[str, set[str]] = {}
    prose = []
    for source in evidence:
        row = source.get("table_row")
        if row:
            label = TABLE.match(row["caption"])
            if label and compact(label.group()).casefold() == name:
                tables.append(source)
        elif source.get("section_title") and mentions(query, words(source["section_title"])):
            sections.setdefault(source["section_title"], set()).add(source["evidence_id"])
            prose.append(source)

    # Leave general synthesis and legacy passages on the standard path. This
    # check applies when a named table has typed measurements and the question
    # names a column and explicitly excludes one condition.
    requested = {
        cell["column"] for source in tables for cell in source["table_row"]["cells"]
        if measurement(cell["value"]) and (mentions(query, words(cell["column"])) or any(
            token.casefold() in query for token in re.findall(r"\b[A-Z][A-Z0-9]{1,}\b", cell["column"])
        ))
    }
    if not requested:
        return None
    if re.search(r"\bcompare\b", question, re.I) and not prose:
        return TableScope([], {}, sections)

    selected = []
    for source in tables:
        row = source["table_row"]
        labels = [cell["value"] for cell in row["cells"] if not measurement(cell["value"])]
        siblings = [(cell["value"], neighbor["table_row"].get("term_definitions", {}))
                    for neighbor in tables if neighbor is not source
                    and neighbor["document_id"] == source["document_id"]
                    and neighbor["page_start"] == source["page_start"]
                    and neighbor["table_row"]["group"] == row["group"]
                    and neighbor["table_row"]["caption"] == row["caption"]
                    for cell in neighbor["table_row"]["cells"] if not measurement(cell["value"])]
        if not any(
            establishes_exclusion(label, siblings, condition)
            and any(mentions(query, words(label)[i:i + 2]) for i in range(len(words(label)) - 1))
            for label in labels
        ):
            continue
        if row["group"] and not any(mentions(query, words(row["group"])[:size])
                                    for size in range(2, len(words(row["group"])) + 1)):
            continue
        cells = [cell for cell in row["cells"] if not measurement(cell["value"]) or cell["column"] in requested]
        values = [cell["value"] for cell in cells if cell["column"] in requested]
        if values:
            selected.append(({**source, "table_row": {**row, "cells": cells}}, values))
    # Multiple plausible rows are left unresolved. Do not let the model use
    # nearby text or a different metric as a fallback for a missing match.
    if len(selected) != 1:
        return TableScope([], {}, sections)
    source, values = selected[0]
    return TableScope([source, *prose], {source["evidence_id"]: values}, sections)
