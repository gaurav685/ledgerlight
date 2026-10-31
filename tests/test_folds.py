"""Tests for ledgerlight.modelling.folds -- the real embargo and fold
construction required by Phase 3 brief §7 / §10. Uses synthetic
DatasetRow objects (not the real DB) so the fold arithmetic itself is
pinned independent of real data drift."""

from __future__ import annotations

import datetime as dt
import uuid

from ledgerlight.modelling.dataset import DatasetRow
from ledgerlight.modelling.folds import build_walk_forward_folds

COMPANY_A = uuid.uuid4()
COMPANY_B = uuid.uuid4()


def _row(company_id: uuid.UUID, as_of: dt.date, label: int, censored: bool = False) -> DatasetRow:
    return DatasetRow(
        company_id=company_id,
        company_name=str(company_id),
        as_of=as_of,
        features={},
        label=None if censored else label,
        censored=censored,
        censor_reason="x" if censored else None,
    )


def test_train_cutoff_is_exactly_24_months_before_test_start() -> None:
    rows = [_row(COMPANY_A, dt.date(2020, 6, 30), 0)]
    folds = build_walk_forward_folds(rows)
    assert len(folds) == 1
    fold = folds[0]
    assert fold.test_start == dt.date(2020, 1, 1)
    assert fold.test_end == dt.date(2021, 1, 1)
    # 12mo horizon + 12mo embargo = 24mo before test_start.
    assert fold.train_cutoff == dt.date(2018, 1, 1)


def test_train_rows_never_fall_within_the_embargo_window() -> None:
    """A row dated exactly at the train cutoff (or later) must never
    appear in train_rows -- its own 12-month forward label window
    would otherwise overlap the embargo or the test period."""
    rows = [
        _row(COMPANY_A, dt.date(2017, 12, 31), 1),  # just before cutoff: in train
        _row(COMPANY_A, dt.date(2018, 1, 1), 1),  # at cutoff: excluded
        _row(COMPANY_A, dt.date(2018, 6, 30), 1),  # inside embargo: excluded
        _row(COMPANY_A, dt.date(2020, 3, 31), 0),  # inside test year: test only
    ]
    folds = build_walk_forward_folds(rows)
    fold = next(f for f in folds if f.test_year == 2020)
    assert [r.as_of for r in fold.train_rows] == [dt.date(2017, 12, 31)]
    assert [r.as_of for r in fold.test_rows] == [dt.date(2020, 3, 31)]


def test_censored_rows_never_appear_in_any_fold() -> None:
    rows = [
        _row(COMPANY_A, dt.date(2019, 1, 31), 1, censored=True),
        _row(COMPANY_A, dt.date(2020, 1, 31), 1),
    ]
    folds = build_walk_forward_folds(rows)
    for fold in folds:
        assert all(not r.censored for r in fold.train_rows)
        assert all(not r.censored for r in fold.test_rows)


def test_one_fold_per_year_with_real_test_rows_only() -> None:
    rows = [
        _row(COMPANY_A, dt.date(2019, 1, 31), 0),
        _row(COMPANY_B, dt.date(2019, 6, 30), 1),
        _row(COMPANY_A, dt.date(2021, 1, 31), 0),
    ]
    folds = build_walk_forward_folds(rows)
    assert [f.test_year for f in folds] == [2019, 2021]
    fold_2019 = folds[0]
    assert len(fold_2019.test_rows) == 2
    assert {r.company_id for r in fold_2019.test_rows} == {COMPANY_A, COMPANY_B}


def test_expanding_window_accumulates_train_rows_across_later_folds() -> None:
    rows = [
        _row(COMPANY_A, dt.date(2017, 1, 31), 0),
        _row(COMPANY_A, dt.date(2018, 1, 31), 0),
        _row(COMPANY_A, dt.date(2021, 6, 30), 0),
        _row(COMPANY_A, dt.date(2022, 6, 30), 0),
    ]
    folds = build_walk_forward_folds(rows)
    fold_2021 = next(f for f in folds if f.test_year == 2021)
    fold_2022 = next(f for f in folds if f.test_year == 2022)
    assert len(fold_2022.train_rows) >= len(fold_2021.train_rows)
