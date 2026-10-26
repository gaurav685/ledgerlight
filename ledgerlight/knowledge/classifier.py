"""Event-type classifiers: (a) the rules/keyword baseline (reused
directly from ledgerlight.knowledge.labeling -- the same function serves
both the silver-label proposer and this baseline classifier, since
they're the same thing), (b) TF-IDF + logistic regression, (c) DeBERTa-
v3 zero-shot NLI (CPU). See docs/knowledge/extraction.md and the Phase 2
evaluation report for the comparison and the production-classifier
choice per event type.

All metrics in this module are computed against SILVER labels (the
keyword proposer's own output, human-corrected where review has
happened) -- never claimed as gold. See the Phase 2 report's
human-gold-review checkpoint.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ledgerlight.knowledge.labeling import propose_event_type

if TYPE_CHECKING:
    from transformers import Pipeline

EVENT_TYPE_CODES = [
    "AUD_RESIGN",
    "PLEDGE_UP",
    "KMP_EXIT",
    "ID_EXIT",
    "RATING_ACT",
    "RESULT_DELAY",
    "AUDIT_QUAL",
    "FORENSIC",
    "RPT_GROWTH",
]
NONE_LABEL = "none"
ALL_LABELS = [*EVENT_TYPE_CODES, NONE_LABEL]

DEBERTA_MODEL_NAME = "MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli"
DEBERTA_MODEL_LICENSE = "MIT"
# Minimum positives/class the brief sets for fine-tuning to even be
# considered. No event type in this corpus reaches it (max is PLEDGE_UP
# at 28) -- see docs/evaluation/phase-2-evaluation.md for the full
# per-class counts and the resulting decision: zero-shot only, no
# fine-tuning attempted.
FINE_TUNE_MIN_POSITIVES_PER_CLASS = 50

_DEBERTA_CANDIDATE_LABELS: dict[str, str] = {
    "AUD_RESIGN": "statutory auditor resignation",
    "PLEDGE_UP": "promoter shareholding pledge increase",
    "KMP_EXIT": "key managerial personnel resignation",
    "ID_EXIT": "independent director resignation",
    "RATING_ACT": "credit rating downgrade or negative outlook",
    "RESULT_DELAY": "delay in filing financial results",
    "AUDIT_QUAL": "qualified or adverse audit opinion",
    "FORENSIC": "forensic audit ordered",
    "RPT_GROWTH": "related party transactions growth",
    NONE_LABEL: "none of the above / unrelated disclosure",
}


def rules_baseline_predict(text: str) -> str:
    return propose_event_type(text) or NONE_LABEL


# --- TF-IDF + logistic regression ------------------------------------------


@dataclass
class TfidfLrModel:
    vectorizer: object
    classifier: object
    classes: list[str]


def train_tfidf_lr(texts: list[str], labels: list[str]) -> TfidfLrModel:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression

    vectorizer = TfidfVectorizer(max_features=5000, ngram_range=(1, 2), min_df=1)
    x = vectorizer.fit_transform(texts)
    classifier = LogisticRegression(max_iter=1000, class_weight="balanced", random_state=42)
    classifier.fit(x, labels)
    return TfidfLrModel(
        vectorizer=vectorizer, classifier=classifier, classes=list(classifier.classes_)
    )


def tfidf_lr_predict(model: TfidfLrModel, texts: list[str]) -> list[str]:
    x = model.vectorizer.transform(texts)  # type: ignore[attr-defined]
    predictions: list[str] = model.classifier.predict(x).tolist()  # type: ignore[attr-defined]
    return predictions


# --- DeBERTa-v3 zero-shot NLI ------------------------------------------------

_zero_shot_pipeline: Pipeline | None = None


def _get_zero_shot_pipeline() -> Pipeline:
    global _zero_shot_pipeline
    if _zero_shot_pipeline is None:
        # Real bug found running this for real: with TOKENIZERS_PARALLELISM
        # unset, the Rust `tokenizers` backend spawns a parallel worker that,
        # on this machine, resolved to an unrelated system Python install
        # instead of this venv's interpreter -- turning a ~20-minute CPU
        # workload (126 examples) into a 13+ hour stall. Must be set before
        # the pipeline is constructed.
        os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
        from transformers import pipeline

        _zero_shot_pipeline = pipeline(
            "zero-shot-classification", model=DEBERTA_MODEL_NAME, device=-1
        )
    return _zero_shot_pipeline


def deberta_zero_shot_predict(text: str, confidence_threshold: float = 0.5) -> tuple[str, float]:
    """Returns (predicted_code, confidence). Falls back to NONE_LABEL if
    the top candidate's score is below confidence_threshold."""
    clf = _get_zero_shot_pipeline()
    candidate_labels = list(_DEBERTA_CANDIDATE_LABELS.values())
    result = clf(text, candidate_labels=candidate_labels, multi_label=False)
    top_label = result["labels"][0]
    top_score = float(result["scores"][0])

    label_to_code = {v: k for k, v in _DEBERTA_CANDIDATE_LABELS.items()}
    code = label_to_code[top_label]
    if top_score < confidence_threshold:
        return NONE_LABEL, top_score
    return code, top_score
