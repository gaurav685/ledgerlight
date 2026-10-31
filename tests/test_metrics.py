"""Tests for ledgerlight.modelling.metrics -- the real Sec7 metrics.
Each test pins a concrete, hand-computable scenario so the arithmetic
itself is verified, not just "it runs"."""

from __future__ import annotations

import datetime as dt
import uuid

import numpy as np

from ledgerlight.modelling.dataset import DatasetRow
from ledgerlight.modelling.metrics import (
    compute_metrics,
    expected_calibration_error,
    lead_time_days_median,
    precision_at_k,
    recall_at_alert_rate,
)

COMPANY_A = uuid.uuid4()
COMPANY_B = uuid.uuid4()


def _row(
    company_id: uuid.UUID,
    as_of: dt.date,
    label: int,
    event_time: dt.datetime | None = None,
) -> DatasetRow:
    return DatasetRow(
        company_id=company_id,
        company_name=str(company_id),
        as_of=as_of,
        features={},
        label=label,
        censored=False,
        censor_reason=None,
        triggering_event_time=event_time,
    )


def test_precision_at_k_counts_real_positives_in_the_top_k_by_score() -> None:
    y = np.array([1.0, 0.0, 1.0, 0.0])
    s = np.array([0.9, 0.8, 0.1, 0.05])
    assert precision_at_k(y, s, 2) == 0.5  # top-2 by score: indices 0,1 -> 1 real positive of 2
    assert precision_at_k(y, s, 4) == 0.5


def test_precision_at_k_returns_none_for_empty_input() -> None:
    assert precision_at_k(np.array([]), np.array([]), 5) is None


def test_recall_at_alert_rate_returns_none_with_zero_real_positives() -> None:
    y = np.array([0.0, 0.0, 0.0])
    s = np.array([0.9, 0.5, 0.1])
    assert recall_at_alert_rate(y, s, 0.5) is None


def test_recall_at_alert_rate_finds_all_real_positives_among_top_scores() -> None:
    y = np.array([1.0, 1.0, 0.0, 0.0])
    s = np.array([0.9, 0.8, 0.2, 0.1])
    # top 50% (k=2) by score are exactly the two real positives.
    assert recall_at_alert_rate(y, s, 0.5) == 1.0


def test_ece_is_zero_for_perfectly_calibrated_scores() -> None:
    y = np.array([0.0, 0.0, 1.0, 1.0])
    s = np.array([0.0, 0.0, 1.0, 1.0])
    ece, bins = expected_calibration_error(y, s, n_bins=2)
    assert ece == 0.0
    assert sum(count for _, _, count in bins) == 4


def test_ece_is_positive_for_badly_miscalibrated_scores() -> None:
    y = np.array([0.0, 0.0, 0.0, 0.0])
    s = np.array([0.9, 0.9, 0.9, 0.9])
    ece, _bins = expected_calibration_error(y, s, n_bins=2)
    assert ece is not None
    assert ece > 0.5


def test_lead_time_counts_each_real_event_once_across_its_company_month_rows() -> None:
    event_time = dt.datetime(2020, 6, 15)
    rows = [
        _row(COMPANY_A, dt.date(2020, 1, 31), 1, event_time),
        _row(COMPANY_A, dt.date(2020, 2, 29), 1, event_time),
        _row(COMPANY_A, dt.date(2020, 3, 31), 1, event_time),
    ]
    scores = {
        (COMPANY_A, dt.date(2020, 1, 31)): 0.2,
        (COMPANY_A, dt.date(2020, 2, 29)): 0.6,  # first as_of crossing the threshold
        (COMPANY_A, dt.date(2020, 3, 31)): 0.9,
    }
    lead_time = lead_time_days_median(rows, scores, threshold=0.5)
    expected_days = (dt.date(2020, 6, 15) - dt.date(2020, 2, 29)).days
    assert lead_time == float(expected_days)


def test_lead_time_is_none_when_no_true_positive_ever_crosses_the_threshold() -> None:
    event_time = dt.datetime(2020, 6, 15)
    rows = [_row(COMPANY_A, dt.date(2020, 1, 31), 1, event_time)]
    scores = {(COMPANY_A, dt.date(2020, 1, 31)): 0.1}
    assert lead_time_days_median(rows, scores, threshold=0.5) is None


def test_compute_metrics_returns_none_pr_auc_and_roc_auc_with_a_single_test_class() -> None:
    rows = [_row(COMPANY_A, dt.date(2020, 1, 31), 0), _row(COMPANY_B, dt.date(2020, 1, 31), 0)]
    scores = {(COMPANY_A, dt.date(2020, 1, 31)): 0.3, (COMPANY_B, dt.date(2020, 1, 31)): 0.7}
    report = compute_metrics(rows, scores, train_prevalence=0.2)
    assert report.pr_auc is None
    assert report.roc_auc is None
    assert report.n == 2


def test_compute_metrics_brier_skill_score_is_positive_when_beating_the_base_rate() -> None:
    rows = [
        _row(COMPANY_A, dt.date(2020, 1, 31), 1),
        _row(COMPANY_B, dt.date(2020, 1, 31), 0),
    ]
    scores = {(COMPANY_A, dt.date(2020, 1, 31)): 0.9, (COMPANY_B, dt.date(2020, 1, 31)): 0.1}
    report = compute_metrics(rows, scores, train_prevalence=0.5)
    assert report.brier_skill_score is not None
    assert report.brier_skill_score > 0.0


def test_compute_metrics_distinct_companies_counts_unique_company_ids() -> None:
    rows = [
        _row(COMPANY_A, dt.date(2020, 1, 31), 0),
        _row(COMPANY_A, dt.date(2020, 2, 29), 0),
        _row(COMPANY_B, dt.date(2020, 1, 31), 0),
    ]
    scores = {
        (COMPANY_A, dt.date(2020, 1, 31)): 0.1,
        (COMPANY_A, dt.date(2020, 2, 29)): 0.1,
        (COMPANY_B, dt.date(2020, 1, 31)): 0.1,
    }
    report = compute_metrics(rows, scores, train_prevalence=0.0)
    assert report.distinct_companies == 2
    assert report.n == 3
