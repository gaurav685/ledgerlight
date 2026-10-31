"""Real §7 metrics, computed directly from real labels and real model
scores on one fold's test rows: PR-AUC versus prevalence, ROC-AUC,
precision@K, recall at a fixed alert rate, Brier score and Brier
skill score versus the real training-fold base rate, ECE plus
reliability-diagram bins, and lead time for true positives. Every
metric that cannot be honestly computed (fewer than two real label
classes, zero real positives) returns `None`, never a fabricated
number.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass, field

import numpy as np
from sklearn.metrics import average_precision_score, roc_auc_score

from ledgerlight.modelling.dataset import DatasetRow
from ledgerlight.modelling.models import RowKey

DEFAULT_ALERT_RATES = (0.01, 0.05, 0.10)
DEFAULT_TOP_K_ABSOLUTE = 50
DEFAULT_RELIABILITY_BINS = 10
DEFAULT_ALERT_THRESHOLD = 0.5


def _labels_and_scores(
    rows: list[DatasetRow], scores: dict[RowKey, float]
) -> tuple[np.ndarray, np.ndarray]:
    y = np.array([row.label for row in rows], dtype=float)
    s = np.array([scores[(row.company_id, row.as_of)] for row in rows], dtype=float)
    return y, s


def precision_at_k(y: np.ndarray, s: np.ndarray, k: int) -> float | None:
    if k <= 0 or len(y) == 0:
        return None
    k = min(k, len(y))
    order = np.argsort(-s)
    top_k = order[:k]
    return float(y[top_k].mean())


def precision_at_top_fraction(y: np.ndarray, s: np.ndarray, fraction: float) -> float | None:
    if len(y) == 0:
        return None
    k = max(1, int(round(len(y) * fraction)))
    return precision_at_k(y, s, k)


def recall_at_alert_rate(y: np.ndarray, s: np.ndarray, rate: float) -> float | None:
    positives = float(y.sum())
    if positives == 0 or len(y) == 0:
        return None
    k = max(1, int(round(len(y) * rate)))
    order = np.argsort(-s)
    top_k = order[: min(k, len(y))]
    return float(y[top_k].sum() / positives)


def expected_calibration_error(
    y: np.ndarray, s: np.ndarray, n_bins: int = DEFAULT_RELIABILITY_BINS
) -> tuple[float | None, list[tuple[float, float, int]]]:
    if len(y) == 0:
        return None, []
    bin_edges = np.linspace(0.0, 1.0, n_bins + 1)
    bin_ids = np.clip(np.digitize(s, bin_edges[1:-1]), 0, n_bins - 1)
    ece = 0.0
    bins: list[tuple[float, float, int]] = []
    for bin_idx in range(n_bins):
        mask = bin_ids == bin_idx
        count = int(mask.sum())
        if count == 0:
            continue
        mean_pred = float(s[mask].mean())
        mean_actual = float(y[mask].mean())
        ece += (count / len(y)) * abs(mean_pred - mean_actual)
        bins.append((mean_pred, mean_actual, count))
    return float(ece), bins


def lead_time_days_median(
    rows: list[DatasetRow], scores: dict[RowKey, float], threshold: float = DEFAULT_ALERT_THRESHOLD
) -> float | None:
    """Median real calendar days from the first as_of whose score
    crosses `threshold` to the real triggering outcome event, for
    real true-positive events only. One real event can span several
    consecutive company-month rows (the forward-window labeling); each
    distinct (company, triggering_event_time) is counted once."""
    by_company: dict[uuid.UUID, list[DatasetRow]] = {}
    for row in rows:
        by_company.setdefault(row.company_id, []).append(row)

    lead_times: list[int] = []
    for company_rows in by_company.values():
        true_positive_rows = [
            row for row in company_rows if row.label == 1 and row.triggering_event_time is not None
        ]
        events: dict[dt.datetime, list[DatasetRow]] = {}
        for row in true_positive_rows:
            assert row.triggering_event_time is not None
            events.setdefault(row.triggering_event_time, []).append(row)
        for event_time, event_rows in events.items():
            above_threshold = [
                row for row in event_rows if scores[(row.company_id, row.as_of)] >= threshold
            ]
            if not above_threshold:
                continue
            first_alert_as_of = min(row.as_of for row in above_threshold)
            lead_times.append((event_time.date() - first_alert_as_of).days)

    if not lead_times:
        return None
    return float(np.median(lead_times))


@dataclass
class MetricsReport:
    n: int
    distinct_companies: int
    prevalence: float
    pr_auc: float | None
    roc_auc: float | None
    precision_at_top_1pct: float | None
    precision_at_top_50: float | None
    recall_at_alert_rate: dict[float, float | None] = field(default_factory=dict)
    brier_score: float | None = None
    brier_skill_score: float | None = None
    ece: float | None = None
    reliability_bins: list[tuple[float, float, int]] = field(default_factory=list)
    lead_time_days_median: float | None = None


def compute_metrics(
    rows: list[DatasetRow],
    scores: dict[RowKey, float],
    train_prevalence: float,
    alert_rates: tuple[float, ...] = DEFAULT_ALERT_RATES,
    alert_threshold: float = DEFAULT_ALERT_THRESHOLD,
) -> MetricsReport:
    """All real, computed only from `rows`/`scores` -- `train_prevalence`
    is the real training-fold base rate (for the Brier skill score),
    passed in rather than re-derived so it can never be the test
    fold's own rate."""
    y, s = _labels_and_scores(rows, scores)
    n = len(y)
    has_two_classes = len(set(y.tolist())) >= 2

    pr_auc = float(average_precision_score(y, s)) if has_two_classes else None
    roc_auc = float(roc_auc_score(y, s)) if has_two_classes else None
    brier = float(np.mean((s - y) ** 2)) if n else None
    brier_base = float(np.mean((train_prevalence - y) ** 2)) if n else None
    brier_skill_score: float | None = None
    if brier is not None and brier_base is not None and brier_base != 0.0:
        brier_skill_score = 1.0 - brier / brier_base
    ece, bins = expected_calibration_error(y, s)

    return MetricsReport(
        n=n,
        distinct_companies=len({row.company_id for row in rows}),
        prevalence=float(y.mean()) if n else 0.0,
        pr_auc=pr_auc,
        roc_auc=roc_auc,
        precision_at_top_1pct=precision_at_top_fraction(y, s, 0.01),
        precision_at_top_50=precision_at_k(y, s, DEFAULT_TOP_K_ABSOLUTE),
        recall_at_alert_rate={rate: recall_at_alert_rate(y, s, rate) for rate in alert_rates},
        brier_score=brier,
        brier_skill_score=brier_skill_score,
        ece=ece,
        reliability_bins=bins,
        lead_time_days_median=lead_time_days_median(rows, scores, alert_threshold),
    )
