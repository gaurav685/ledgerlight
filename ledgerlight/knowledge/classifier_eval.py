"""Evaluation harness for the three classifiers (rules baseline, TF-IDF+LR,
DeBERTa zero-shot) against SILVER labels, split by dev/validation/test
(ledgerlight.knowledge.label_split). Compare on validation; report once
on test -- test is never used to tune anything.
"""

from __future__ import annotations

from dataclasses import dataclass
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


def print_report(report: ClassificationReport) -> None:
    print(f"\n-- {report.method} (n={report.n_examples}) --")
    print(f"{'label':<16} {'precision':>10} {'recall':>8} {'f1':>8} {'support':>8}")
    for c in report.per_class:
        print(f"{c.label:<16} {c.precision:>10.3f} {c.recall:>8.3f} {c.f1:>8.3f} {c.support:>8}")
    print(f"macro_f1: {report.macro_f1:.3f}")
    print(f"confusion_matrix (rows=true, cols=pred, order={report.labels_order}):")
    for row in report.confusion_matrix:
        print("  " + " ".join(f"{v:>4}" for v in row))
