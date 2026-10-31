"""Tests for ledgerlight.modelling.leakage -- the real Sec7 leakage
checks. Each test pins a concrete real-or-synthetic scenario:
a genuine violation that must be caught, a clean case that must pass,
and the deliberately leaky synthetic feature that must be flagged."""

from __future__ import annotations

import datetime as dt
import uuid

from ledgerlight.modelling.dataset import DatasetRow
from ledgerlight.modelling.folds import build_walk_forward_folds
from ledgerlight.modelling.leakage import (
    check_embargo_enforced,
    check_outcome_date_after_as_of,
    permute_labels,
    shift_features_forward,
    univariate_pr_auc_flags,
)

COMPANY_A = uuid.uuid4()
COMPANY_B = uuid.uuid4()


def _row(
    company_id: uuid.UUID,
    as_of: dt.date,
    label: int | None,
    censored: bool = False,
    event_time: dt.datetime | None = None,
    features: dict[str, float | None] | None = None,
) -> DatasetRow:
    return DatasetRow(
        company_id=company_id,
        company_name=str(company_id),
        as_of=as_of,
        features=features or {},
        label=label,
        censored=censored,
        censor_reason="x" if censored else None,
        triggering_event_time=event_time,
    )


def test_outcome_date_check_passes_for_a_real_valid_label() -> None:
    rows = [_row(COMPANY_A, dt.date(2020, 1, 31), 1, event_time=dt.datetime(2020, 6, 1))]
    assert check_outcome_date_after_as_of(rows) == []


def test_outcome_date_check_catches_an_event_before_as_of() -> None:
    rows = [_row(COMPANY_A, dt.date(2020, 6, 30), 1, event_time=dt.datetime(2020, 1, 1))]
    violations = check_outcome_date_after_as_of(rows)
    assert len(violations) == 1


def test_outcome_date_check_catches_a_positive_label_with_no_event_time() -> None:
    rows = [_row(COMPANY_A, dt.date(2020, 1, 31), 1, event_time=None)]
    violations = check_outcome_date_after_as_of(rows)
    assert len(violations) == 1


def test_outcome_date_check_ignores_censored_and_negative_rows() -> None:
    rows = [
        _row(COMPANY_A, dt.date(2020, 1, 31), None, censored=True),
        _row(COMPANY_A, dt.date(2020, 2, 29), 0),
    ]
    assert check_outcome_date_after_as_of(rows) == []


def test_embargo_check_passes_on_real_fold_construction() -> None:
    rows = [
        _row(COMPANY_A, dt.date(2018, 1, 31), 0),
        _row(COMPANY_A, dt.date(2020, 6, 30), 1, event_time=dt.datetime(2020, 7, 1)),
    ]
    folds = build_walk_forward_folds(rows)
    assert check_embargo_enforced(folds) == []


def test_embargo_check_catches_a_tampered_fold() -> None:
    rows = [
        _row(COMPANY_A, dt.date(2019, 6, 30), 0),
        _row(COMPANY_A, dt.date(2020, 6, 30), 1, event_time=dt.datetime(2020, 7, 1)),
    ]
    folds = build_walk_forward_folds(rows)
    fold_2020 = next(f for f in folds if f.test_year == 2020)
    fold_2020.train_rows.append(_row(COMPANY_A, dt.date(2019, 6, 30), 0))
    # Tamper the cutoff itself to simulate a broken fold builder.
    fold_2020.train_cutoff = dt.date(2020, 1, 1)
    violations = check_embargo_enforced(folds)
    assert len(violations) >= 1


def test_permute_labels_keeps_the_real_label_multiset_but_reassigns_rows() -> None:
    rows = [
        _row(COMPANY_A, dt.date(2020, 1, 31), 1),
        _row(COMPANY_A, dt.date(2020, 2, 29), 0),
        _row(COMPANY_B, dt.date(2020, 1, 31), 0),
        _row(COMPANY_B, dt.date(2020, 2, 29), 0),
    ]
    permuted = permute_labels(rows, seed=0)
    assert sorted(row.label for row in permuted) == sorted(row.label for row in rows)
    assert len(permuted) == len(rows)
    assert all(not row.censored for row in permuted)


def test_shift_features_forward_drops_rows_with_no_real_later_snapshot() -> None:
    rows = [
        _row(COMPANY_A, dt.date(2020, 1, 31), 0, features={"ret_1m": 0.1}),
        _row(COMPANY_A, dt.date(2020, 2, 29), 1, features={"ret_1m": 0.2}),
    ]
    shifted = shift_features_forward(rows, months=1)
    assert len(shifted) == 1
    assert shifted[0].as_of == dt.date(2020, 1, 31)
    assert shifted[0].features == {"ret_1m": 0.2}


def test_univariate_pr_auc_flags_catches_a_deliberately_leaky_feature() -> None:
    """The deliberately leaky synthetic feature required by Sec7:
    a feature set equal to the real label itself must be caught by
    the univariate PR-AUC flag -- proving the detection mechanism
    actually works, not just that it runs."""
    rows = [
        _row(COMPANY_A, dt.date(2020, 1, 31), 1, features={"leaky": 1.0, "real_feature": 0.3}),
        _row(COMPANY_A, dt.date(2020, 2, 29), 0, features={"leaky": 0.0, "real_feature": 0.31}),
        _row(COMPANY_B, dt.date(2020, 1, 31), 1, features={"leaky": 1.0, "real_feature": -0.1}),
        _row(COMPANY_B, dt.date(2020, 2, 29), 0, features={"leaky": 0.0, "real_feature": -0.11}),
    ]
    flags = univariate_pr_auc_flags(rows, ["leaky", "real_feature"], threshold=0.95)
    assert "leaky" in flags
    assert flags["leaky"] == 1.0


def test_univariate_pr_auc_flags_returns_empty_with_a_single_class() -> None:
    rows = [_row(COMPANY_A, dt.date(2020, 1, 31), 0, features={"x": 1.0})]
    assert univariate_pr_auc_flags(rows, ["x"]) == {}
