"""Tests for ledgerlight.modelling.ablation. merge_event_candidate_features
is tested against a fake session (no real DB); run_lightgbm_ablation_arm
is tested directly against synthetic DatasetRow data to confirm the
wiring (pooled test rows cover every fold's test rows exactly once,
feature_names on the result match what was requested)."""

from __future__ import annotations

import datetime as dt
import uuid

from ledgerlight.modelling.ablation import (
    load_event_candidate_feature_rows,
    run_lightgbm_ablation_arm,
)
from ledgerlight.modelling.dataset import DatasetRow
from ledgerlight.modelling.folds import build_walk_forward_folds

COMPANY_A = uuid.uuid4()
COMPANY_B = uuid.uuid4()


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeSession:
    def __init__(self, rows):
        self._rows = rows

    def execute(self, *_args, **_kwargs):
        return _FakeResult(self._rows)


def _row(company_id: uuid.UUID, as_of: dt.date, label: int, features=None) -> DatasetRow:
    return DatasetRow(
        company_id=company_id,
        company_name=str(company_id),
        as_of=as_of,
        features=features or {},
        label=label,
        censored=False,
        censor_reason=None,
    )


def test_load_event_candidate_feature_rows_merges_multiple_rows_per_key() -> None:
    as_of = dt.date(2020, 1, 31)
    fake_rows = [
        (COMPANY_A, as_of, {"aud_resign_candidate_count_12m": 1}),
        (COMPANY_A, as_of, {"kmp_exit_candidate_count_12m": 2}),
    ]
    session = _FakeSession(fake_rows)
    merged, feature_names = load_event_candidate_feature_rows(session, [COMPANY_A])
    assert merged[(COMPANY_A, as_of)] == {
        "aud_resign_candidate_count_12m": 1,
        "kmp_exit_candidate_count_12m": 2,
    }
    assert feature_names == ["aud_resign_candidate_count_12m", "kmp_exit_candidate_count_12m"]


def test_load_event_candidate_feature_rows_empty_when_no_rows() -> None:
    session = _FakeSession([])
    merged, feature_names = load_event_candidate_feature_rows(session, [COMPANY_A])
    assert merged == {}
    assert feature_names == []


def test_run_lightgbm_ablation_arm_pools_every_fold_test_row_exactly_once() -> None:
    rows = [
        _row(COMPANY_A, dt.date(2018, 1, 31), 0, {"ret_1m": 0.1}),
        _row(COMPANY_B, dt.date(2019, 6, 30), 1, {"ret_1m": -0.1}),
        _row(COMPANY_A, dt.date(2021, 3, 31), 0, {"ret_1m": 0.2}),
    ]
    folds = build_walk_forward_folds(rows)
    result = run_lightgbm_ablation_arm(rows, ["ret_1m"])
    all_test_keys = {(row.company_id, row.as_of) for fold in folds for row in fold.test_rows}
    assert result.pooled_metrics.n == len(all_test_keys)
    assert result.feature_names == ["ret_1m"]
