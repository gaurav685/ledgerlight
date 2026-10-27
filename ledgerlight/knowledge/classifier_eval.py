"""Evaluation harness for the three classifiers (rules baseline, TF-IDF+LR,
DeBERTa zero-shot) against SILVER labels, split by dev/validation/test
(ledgerlight.knowledge.label_split). Compare on validation; report once
on test -- test is never used to tune anything.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from ledgerlight.knowledge.classifier import ALL_LABELS, NONE_LABEL
from ledgerlight.knowledge.models import Chunk, LabelItem


@dataclass
class LabelledExample:
    chunk_id: UUID
    text: str
    label: str  # final label: corrected_event_type_code if corrected, else proposed


def load_split(session: Session, split: str) -> list[LabelledExample]:
    rows = session.execute(
        select(LabelItem, Chunk.text)
        .join(Chunk, Chunk.id == LabelItem.chunk_id)
        .where(LabelItem.split == split, LabelItem.chunk_id.is_not(None))
    ).all()

    examples = []
    for item, text in rows:
        if item.review_status == "rejected" or item.chunk_id is None:
            continue
        label = item.corrected_event_type_code or item.proposed_event_type_code
        examples.append(LabelledExample(chunk_id=item.chunk_id, text=text, label=label))
    return examples


def load_gold_split(session: Session, split: str) -> list[LabelledExample]:
    """Same as `load_split`, but restricted to GOLD items only
    (`label_source='human_reviewed'`) -- used for classifier selection
    (Phase 3 §1.3) so a method is never selected by comparing against
    its own silver proposals (the circularity that made `rules_baseline`
    score a perfect, meaningless 1.000 in Phase 2)."""
    rows = session.execute(
        select(LabelItem, Chunk.text)
        .join(Chunk, Chunk.id == LabelItem.chunk_id)
        .where(
            LabelItem.split == split,
            LabelItem.chunk_id.is_not(None),
            LabelItem.label_source == "human_reviewed",
        )
    ).all()

    examples = []
    for item, text in rows:
        if item.review_status == "rejected" or item.chunk_id is None:
            continue
        label = item.corrected_event_type_code or item.proposed_event_type_code
        examples.append(LabelledExample(chunk_id=item.chunk_id, text=text, label=label))
    return examples


@dataclass
class ClassMetrics:
    label: str
    precision: float
    recall: float
    f1: float
    support: int


@dataclass
class ClassificationReport:
    method: str
    per_class: list[ClassMetrics]
    macro_f1: float
    confusion_matrix: list[list[int]]
    labels_order: list[str]
    n_examples: int


def evaluate_predictions(method: str, y_true: list[str], y_pred: list[str]) -> ClassificationReport:
    from sklearn.metrics import confusion_matrix as sk_confusion_matrix
    from sklearn.metrics import precision_recall_fscore_support

    labels_order = [label for label in ALL_LABELS if label in set(y_true) | set(y_pred)]
    if not labels_order:
        labels_order = [NONE_LABEL]

    precisions, recalls, f1s, supports = precision_recall_fscore_support(
        y_true, y_pred, labels=labels_order, zero_division=0
    )
    per_class = [
        ClassMetrics(label=label, precision=float(p), recall=float(r), f1=float(f), support=int(s))
        for label, p, r, f, s in zip(labels_order, precisions, recalls, f1s, supports, strict=True)
    ]
    macro_f1 = float(sum(c.f1 for c in per_class) / len(per_class)) if per_class else 0.0
    cm = sk_confusion_matrix(y_true, y_pred, labels=labels_order).tolist()

    return ClassificationReport(
        method=method,
        per_class=per_class,
        macro_f1=macro_f1,
        confusion_matrix=cm,
        labels_order=labels_order,
        n_examples=len(y_true),
    )


MIN_SUPPORT_FOR_SELECTION = 5


@dataclass
class PerClassSelection:
    event_type: str
    support: int
    method_f1: dict[str, float]
    selected_method: str | None  # None when support == 0 (no gold data to select on)
    f1_ci: dict[str, tuple[float, float]]  # bootstrap 95% CI per method, by F1
    insufficient_support: bool
    method_precision: dict[str, float] = field(default_factory=dict)
    precision_ci: dict[str, tuple[float, float]] = field(default_factory=dict)


def _bootstrap_metric_ci(
    y_true: list[str],
    y_pred: list[str],
    label: str,
    metric_index: int,
    *,
    seed: int = 42,
    n_resamples: int = 2000,
) -> tuple[float, float]:
    """Bootstrap 95% CI for one label's precision (metric_index=0),
    recall (1), or F1 (2), resampling the paired (true, pred) tuples
    with replacement. Deterministic given the seed."""
    import random

    from sklearn.metrics import precision_recall_fscore_support

    n = len(y_true)
    if n == 0:
        return (0.0, 0.0)
    rng = random.Random(seed)
    values = []
    for _ in range(n_resamples):
        idxs = [rng.randrange(n) for _ in range(n)]
        yt = [y_true[i] for i in idxs]
        yp = [y_pred[i] for i in idxs]
        metrics = precision_recall_fscore_support(yt, yp, labels=[label], zero_division=0)
        values.append(float(metrics[metric_index][0]))
    values.sort()
    lo = values[int(0.025 * n_resamples)]
    hi = values[int(0.975 * n_resamples)]
    return (lo, hi)


def bootstrap_f1_ci(
    y_true: list[str], y_pred: list[str], label: str, *, seed: int = 42, n_resamples: int = 2000
) -> tuple[float, float]:
    return _bootstrap_metric_ci(y_true, y_pred, label, 2, seed=seed, n_resamples=n_resamples)


def bootstrap_precision_ci(
    y_true: list[str], y_pred: list[str], label: str, *, seed: int = 42, n_resamples: int = 2000
) -> tuple[float, float]:
    return _bootstrap_metric_ci(y_true, y_pred, label, 0, seed=seed, n_resamples=n_resamples)


def select_production_classifier_per_class(
    gold_examples: list[LabelledExample],
    predictions_by_method: dict[str, list[str]],
    *,
    min_support: int = MIN_SUPPORT_FOR_SELECTION,
) -> dict[str, PerClassSelection]:
    """Per event-type class, picks the method with the highest F1 on
    GOLD validation examples only. A class with 0 gold-validation
    support gets `selected_method=None` (nothing to select on --
    callers must fall back explicitly, not silently). Classes with
    `0 < support < min_support` still get a nominal selection, but
    `insufficient_support=True` so callers don't over-trust it."""
    y_true = [e.label for e in gold_examples]
    results: dict[str, PerClassSelection] = {}

    for cls in ALL_LABELS:
        support = y_true.count(cls)
        if support == 0:
            results[cls] = PerClassSelection(
                event_type=cls,
                support=0,
                method_f1={},
                selected_method=None,
                f1_ci={},
                insufficient_support=True,
            )
            continue

        method_f1: dict[str, float] = {}
        method_precision: dict[str, float] = {}
        f1_ci: dict[str, tuple[float, float]] = {}
        precision_ci: dict[str, tuple[float, float]] = {}
        for method, y_pred in predictions_by_method.items():
            report = evaluate_predictions(method, y_true, y_pred)
            class_metrics = next((c for c in report.per_class if c.label == cls), None)
            f1_for_class = class_metrics.f1 if class_metrics else 0.0
            precision_for_class = class_metrics.precision if class_metrics else 0.0
            method_f1[method] = f1_for_class
            method_precision[method] = precision_for_class
            f1_ci[method] = bootstrap_f1_ci(y_true, y_pred, cls)
            precision_ci[method] = bootstrap_precision_ci(y_true, y_pred, cls)

        selected = max(method_f1.items(), key=lambda kv: kv[1])[0]
        results[cls] = PerClassSelection(
            event_type=cls,
            support=support,
            method_f1=method_f1,
            selected_method=selected,
            f1_ci=f1_ci,
            insufficient_support=support < min_support,
            method_precision=method_precision,
            precision_ci=precision_ci,
        )
    return results


def print_report(report: ClassificationReport) -> None:
    print(f"\n-- {report.method} (n={report.n_examples}) --")
    print(f"{'label':<16} {'precision':>10} {'recall':>8} {'f1':>8} {'support':>8}")
    for c in report.per_class:
        print(f"{c.label:<16} {c.precision:>10.3f} {c.recall:>8.3f} {c.f1:>8.3f} {c.support:>8}")
    print(f"macro_f1: {report.macro_f1:.3f}")
    print(f"confusion_matrix (rows=true, cols=pred, order={report.labels_order}):")
    for row in report.confusion_matrix:
        print("  " + " ".join(f"{v:>4}" for v in row))
