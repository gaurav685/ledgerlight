"""Tests for ledgerlight.modelling.backtest -- the real Sec6/7
orchestrator. Uses small synthetic data to confirm the wiring (every
model produces a score for every test row, pooled results cover every
fold's test rows exactly once) without depending on the real DB."""

from __future__ import annotations

import datetime as dt
import uuid

from ledgerlight.modelling.backtest import MODEL_NAMES, run_backtest
from ledgerlight.modelling.coverage import VerifiedCoverage
from ledgerlight.modelling.dataset import DatasetRow

COMPANY_A = uuid.uuid4()
COMPANY_B = uuid.uuid4()


def _row(company_id: uuid.UUID, as_of: dt.date, label: int) -> DatasetRow:
    return DatasetRow(
        company_id=company_id,
        company_name=str(company_id),
        as_of=as_of,
        features={"ret_1m": 0.1, "current_rating_ordinal": 5.0, "downgrades_count_12m": 0.0},
        label=label,
        censored=False,
        censor_reason=None,
    )


def _fake_coverage() -> VerifiedCoverage:
    return VerifiedCoverage(
        window_start=dt.date(2015, 1, 1),
        window_end=dt.date(2026, 1, 1),
        company_ids=[COMPANY_A, COMPANY_B],
        company_names=["A", "B"],
        ibbi_known_at_range=(dt.datetime(2015, 1, 1), dt.datetime(2026, 1, 1)),
        care_known_at_range=(dt.datetime(2015, 1, 1), dt.datetime(2026, 1, 1)),
    )


def test_every_model_scores_every_test_row_in_every_fold() -> None:
    rows = [
        _row(COMPANY_A, dt.date(2018, 1, 31), 0),
        _row(COMPANY_B, dt.date(2019, 6, 30), 1),
        _row(COMPANY_A, dt.date(2021, 3, 31), 0),
    ]
    result = run_backtest(rows, _fake_coverage())
    assert len(result.folds) > 0
    for fold in result.folds:
        outputs = result.per_fold_outputs[fold.test_year]
        assert set(outputs) == set(MODEL_NAMES)
        for output in outputs.values():
            for row in fold.test_rows:
                assert (row.company_id, row.as_of) in output.scores


def test_pooled_outputs_cover_exactly_the_union_of_fold_test_rows() -> None:
    rows = [
        _row(COMPANY_A, dt.date(2018, 1, 31), 0),
        _row(COMPANY_B, dt.date(2019, 6, 30), 1),
        _row(COMPANY_A, dt.date(2021, 3, 31), 0),
    ]
    result = run_backtest(rows, _fake_coverage())
    all_test_keys = {(row.company_id, row.as_of) for fold in result.folds for row in fold.test_rows}
    for name in MODEL_NAMES:
        assert set(result.pooled_outputs[name].scores) == all_test_keys


def test_no_rows_produces_no_folds_and_no_crash() -> None:
    result = run_backtest([], _fake_coverage())
    assert result.folds == []
    for name in MODEL_NAMES:
        assert result.pooled_outputs[name].scores == {}
