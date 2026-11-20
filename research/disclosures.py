"""Targeted, citable checks for components of a reproducible experiment."""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Disclosure:
    label: str
    reported: str
    limitation: str = ""


NUMBER = r"[+-]?(?:\d+(?:\.\d+)?|\.\d+)(?:[eE][+-]?\d+)?"
REPOSITORY = r"https?://(?:www\.)?(?:github\.com|gitlab\.com)/[\w.-]+/[\w.-]*[\w]"
CHECKS = {
    "Dataset identity and version": (
        Disclosure("Dataset release or version",
                   r"\bdataset (?:release|version)\s*(?:of|was|[=:])?\s*v?\d+(?:\.\d+)*\b"),
        Disclosure("Data access",
                   r"\b(?:the |our )?(?:dataset|data) (?:is|are) (?:publicly|freely) available\b",
                   r"\b(?:the |our )?(?:dataset|data) (?:is|are) (?:not publicly available|available (?:only )?upon (?:reasonable )?request|restricted)\b"),
    ),
    "Preprocessing": (
        Disclosure("Input dimensions", r"\b(?:resized|cropped)\s+(?:to\s+)?\d+\s*[×x]\s*\d+\b"),
        Disclosure("Normalization constants", rf"\b(?:normalization )?(?:mean|standard deviation)\s*(?:of|[=:])\s*{NUMBER}"),
    ),
    "Data splits": (
        Disclosure("Split fractions or fold count",
                   r"\b(?:\d+[- ]fold\s+cross[- ]validation|\d+\s*%\s+(?:of (?:the )?data\s+)?(?:for\s+)?(?:training|testing|validation))\b"),
        Disclosure("Leakage or grouping control",
                   r"\b(?:patient|subject|participant|user|group)[- ](?:level|wise) (?:split|partition|cross[- ]validation)\b|"
                   r"\bno (?:patients|participants|subjects|samples) overlapped between\b"),
    ),
    "Model implementation": (
        Disclosure("Named implementation or checkpoint",
                   r"\b(?:ResNet[- ]?\d+|VGG[- ]?\d+|ViT[- ]?[A-Z0-9/]+|BERT[- ](?:base|large))\b"),
        Disclosure("Parameter count", r"\b\d+(?:\.\d+)?\s+(?:million|billion)\s+(?:trainable )?parameters\b"),
    ),
    "Training settings": (
        Disclosure("Epoch count", r"\b(?:epochs?\s*(?:was|were|of|[=:])\s*\d+|\d+\s+epochs)\b"),
        Disclosure("Batch size", r"\bbatch size\s*(?:of|was|[=:])\s*\d+\b"),
        Disclosure("Learning rate", rf"\blearning rate\s*(?:of|was|[=:])\s*{NUMBER}"),
    ),
    "Optimizer and schedule": (
        Disclosure("Optimizer name", r"\b(?:AdamW?|SGD|RMSprop|AdaGrad)\b"),
        Disclosure("Learning-rate schedule", r"\b(?:cosine annealing|linear warmup|step decay|ReduceLROnPlateau)\b"),
    ),
    "Random seeds": (
        Disclosure("Exact seed values", r"\b(?:random seeds?|seeds?)\s*(?:was|were|[=:])\s*\d+(?:\s*(?:,|and)\s*\d+)*\b"),
        Disclosure("Number of repeats", r"\b\d+\s+(?:independent runs?|random seeds?|repeats)\b"),
    ),
    "Evaluation protocol": (
        Disclosure("Metric averaging", r"\b(?:macro|micro|weighted)[- ]averag(?:e|ed|ing)\b"),
        Disclosure("Decision threshold", rf"\b(?:decision |classification )?threshold\s*(?:of|was|[=:])\s*{NUMBER}"),
    ),
    "Hardware and compute": (
        Disclosure("Accelerator model", r"\b(?:RTX\s*\d{3,5}|A100|H100|V100|TPU\s*v\d+)\b"),
        Disclosure("Compute budget", rf"\b{NUMBER}\s+(?:GPU|TPU)[- ]hours?\b"),
    ),
    "Code and artifacts": (
        Disclosure("Repository locator", REPOSITORY),
        Disclosure("Version pin", r"\b(?:commit|revision)\s*(?:SHA|hash|[=:])?\s*\b[a-f0-9]{7,40}\b|"
                   r"\brelease tag\s*(?:was|[=:])?\s*v\d+(?:\.\d+)+\b"),
        Disclosure("Code availability", r"\b(?:code|implementation) (?:is|was) (?:publicly |freely )?(?:available at|released at|open source)\b",
                   r"\b(?:code|implementation) (?:is|was|will be) (?:not (?:publicly )?(?:available|released)|"
                   r"available (?:only )?upon request|released (?:after publication|upon acceptance))\b"),
    ),
    "Statistical uncertainty": (
        Disclosure("Uncertainty calculation",
                   r"\b(?:bootstrap|Wilson|Clopper[- ]Pearson|normal approximation) (?:method|confidence interval|interval)s?\b"),
        Disclosure("Reported uncertainty",
                   rf"\b(?:{NUMBER}\s*±\s*{NUMBER}|\d{{2}}(?:\.\d+)?\s*%\s+(?:CI|confidence interval)\s*[=:]?\s*"
                   rf"\[\s*{NUMBER}\s*,\s*{NUMBER}\s*\])"),
    ),
}


def statement_excerpt(text: str, hit: re.Match) -> str:
    boundaries = list(re.finditer(r"[.!?](?=\s|$)", text))
    start = max((point.end() for point in boundaries if point.end() <= hit.start()), default=0)
    end = next((point.end() for point in boundaries if point.end() >= hit.end()), len(text))
    if end - start > 320:
        if hit.start() - start > 125:
            gap = text.rfind(" ", hit.start() - 125, hit.start())
            start = gap + 1 if gap != -1 else hit.start()
        if end - hit.end() > 150:
            end = text.find(" ", hit.end(), hit.end() + 150)
            if end == -1:
                end = hit.end()
    return text[start:end].strip()


def assess_disclosures(label: str, passages: list[dict]) -> list[dict]:
    results = []
    sources = [(" ".join(passage["text"].split()), passage) for passage in passages]
    for check in CHECKS[label]:
        evidence = {}
        for text, passage in sources:
            for kind, expression in (("reported", check.reported), ("limitation", check.limitation)):
                if not expression or kind in evidence:
                    continue
                hit = re.search(expression, text, re.IGNORECASE)
                if hit:
                    evidence[kind] = {
                        "kind": kind, "match": hit.group(0),
                        "excerpt": statement_excerpt(text, hit),
                        "source": {key: passage[key] for key in ("document_id", "chunk_id", "page_start", "page_end")},
                    }
            if len(evidence) == (2 if check.limitation else 1):
                break
        status = "mixed" if len(evidence) == 2 else next(iter(evidence), "not_located")
        results.append({"label": check.label, "status": status, "evidence": list(evidence.values())})
    return results
