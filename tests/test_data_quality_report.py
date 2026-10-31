"""Tests for ledgerlight.modelling.data_quality_report -- real
missingness-by-feature-and-year arithmetic, including censored rows
in the denominator since missingness reflects real snapshot coverage,
not only the labeled subset."""

from __future__ import annotations

import datetime as dt
import uuid

import pytest

from ledgerlight.modelling.data_quality_report import compute_missingness_by_feature_and_year
from ledgerlight.modelling.dataset import DatasetRow

COMPANY_A = uuid.uuid4()


def _row(as_of: dt.date, features: dict[str, float | None], censored: bool = False) -> DatasetRow:
    return DatasetRow(
        company_id=COMPANY_A,
        company_name="A",
        as_of=as_of,
        features=features,
        label=None if censored else 0,
        censored=censored,
        censor_reason="x" if censored else None,
    )


def test_missingness_is_the_real_fraction_of_rows_without_the_feature() -> None:
    rows = [
        _row(dt.date(2020, 1, 31), {"x": 1.0}),
        _row(dt.date(2020, 2, 29), {"x": None}),
        _row(dt.date(2020, 3, 31), {}),
    ]
    report = compute_missingness_by_feature_and_year(rows, ["x"])
    assert report.by_feature_and_year["x"][2020] == pytest.approx(2 / 3)


def test_missingness_is_bucketed_by_real_as_of_year() -> None:
    rows = [
        _row(dt.date(2019, 12, 31), {"x": 1.0}),
        _row(dt.date(2020, 1, 31), {"x": None}),
    ]
    report = compute_missingness_by_feature_and_year(rows, ["x"])
    assert report.by_feature_and_year["x"][2019] == 0.0
    assert report.by_feature_and_year["x"][2020] == 1.0


def test_censored_rows_count_toward_missingness_denominator() -> None:
    rows = [
        _row(dt.date(2020, 1, 31), {"x": None}, censored=True),
        _row(dt.date(2020, 2, 29), {"x": 1.0}),
    ]
    report = compute_missingness_by_feature_and_year(rows, ["x"])
    assert report.by_feature_and_year["x"][2020] == 0.5
