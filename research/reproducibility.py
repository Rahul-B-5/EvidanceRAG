"""Evidence-first checklist for reproducing an experiment from a paper."""

import re
from dataclasses import dataclass

from app.retrieval.keyword import search_keyword


@dataclass(frozen=True)
class Rule:
    label: str
    query: str
    detail: str
    mention: str
    verify: str


RULES = (
    Rule("Dataset identity and version", "dataset OR benchmark OR samples OR corpus",
         r"\bdataset\s+(?:version|v\.?\s*\d)|\b\d[\d,]*\s+(?:images|samples|observations|records)\b",
         r"\b(?:dataset|benchmark|corpus)\b", "Confirm the dataset name, release, access and inclusion criteria."),
    Rule("Preprocessing", "preprocessing OR normalized OR resized OR augmented",
         r"\b(?:resized|cropped)\s+(?:to\s+)?\d+\s*[×x]\s*\d+|\b(?:mean|standard deviation)\s*(?:of|=|:)\s*[\d.]",
         r"\b(?:preprocess\w*|normaliz\w*|resiz\w*|augment\w*)\b", "Recreate transformation order and distinguish train-time augmentation from evaluation preprocessing."),
    Rule("Data splits", "split OR holdout OR cross-validation",
         r"\b\d+[- ]fold\s+cross[- ]validation\b|\b\d+\s*%\s+(?:of (?:the )?data\s+)?(?:for\s+)?(?:training|testing|validation)\b",
         r"\b(?:held[- ]out|split|cross[- ]validation)\b", "Verify split proportions, grouping, stratification and leakage controls."),
    Rule("Model implementation", "backbone OR implementation OR architecture OR parameters",
         r"\b(?:ResNet[- ]?\d+|VGG[- ]?\d+|ViT[- ]?[A-Z0-9/]+|\d+\s+(?:million|billion)\s+parameters)\b",
         r"\b(?:backbone|architecture|implementation|encoder)\b", "Confirm architecture variant, initialization, implementation version and trainable layers."),
    Rule("Training settings", 'epoch OR "batch size" OR "learning rate" OR hyperparameter',
         r"\b(?:batch size|learning rate|epochs?)\s*(?:was|of|=|:)\s*[\d.]|\b\d+\s+epochs\b",
         r"\b(?:epoch\w*|batch size|learning rate|hyperparameter\w*)\b", "Record batch size, learning rate, epochs and stopping rule."),
    Rule("Optimizer and schedule", "optimizer OR scheduler OR Adam OR SGD",
         r"\b(?:AdamW?|SGD|RMSprop|cosine annealing|linear warmup)\b",
         r"\b(?:optimi[sz]er|scheduler|warmup)\b", "Confirm optimizer parameters and how the schedule changes across steps."),
    Rule("Random seeds", "seed OR random",
         r"\b(?:random seeds?|seeds?)\s*(?:was|were|[=:])\s*\d+",
         r"\b(?:random seeds?|seeds?)\b", "Find the exact seed values and order, then repeat runs to check variance."),
    Rule("Evaluation protocol", "metric OR evaluation OR validation OR threshold",
         r"\b(?:threshold|confidence level)\s*(?:of|was|=|:)\s*[\d.]|\b(?:macro|micro)[- ]averaged\b",
         r"\b(?:evaluation|threshold|protocol|metric)\b", "Confirm metric definitions, thresholds, averaging and which split was evaluated."),
    Rule("Hardware and compute", "gpu OR hardware OR runtime OR compute",
         r"\b(?:RTX\s*\d{3,5}|A100|H100|V100|TPU\s*v\d+|\d+(?:\.\d+)?\s+GPU[- ]hours?)\b",
         r"\b(?:GPU|hardware|compute|runtime|TPU)\b", "Confirm accelerator count, memory, precision and elapsed training time."),
    Rule("Code and artifacts", "github OR repository OR checkpoints OR artifacts",
         r"https?://(?:www\.)?(?:github\.com|gitlab\.com|zenodo\.org)/[^\s<>]+",
         r"\b(?:repository|checkpoints?|artifacts?|code (?:is|will be) available)\b", "Verify the linked repository belongs to this study, check access and pin the release or commit."),
    Rule("Statistical uncertainty", '"confidence interval" OR "standard deviation" OR variance OR significance',
         r"\b\d{2}(?:\.\d+)?\s*%\s+confidence intervals?\b|\d+(?:\.\d+)?\s*±\s*\d+(?:\.\d+)?|\bp\s*[<=>]\s*0?\.\d+",
         r"\b(?:confidence interval|standard deviation|variance|significan\w*)\b", "Verify sample size, independent repeats and how uncertainty was calculated."),
)


def assess_document(document_id: int, workspace_id: int | None) -> list[dict]:
    assessment = []
    for rule in RULES:
        best = None
        for passage in search_keyword(rule.query, top_k=5, document_id=document_id, workspace_id=workspace_id):
            if passage["document_id"] != document_id:
                continue
            text = " ".join(passage["text"].split())
            detail = re.search(rule.detail, text, re.IGNORECASE)
            match = detail or re.search(rule.mention, text, re.IGNORECASE)
            if match is None:
                continue
            if best is None or detail:
                best = {
                    "status": "specific_detail" if detail else "mention",
                    "matched_text": match.group(0),
                    "excerpt": text[max(0, match.start() - 160):match.end() + 200].strip(),
                    "source": {key: passage[key] for key in ("document_id", "chunk_id", "page_start", "page_end")},
                }
            if detail:
                break
        assessment.append({"label": rule.label, "verify": rule.verify,
                           **(best or {"status": "not_located", "matched_text": None, "excerpt": None, "source": None})})
    return assessment
