"""Tests for ledgerlight.modelling.sensitivity -- the user's explicit
condition (2026-10-31) to evaluate rating-default-only and IBBI-only
outcome variants alongside the combined PRIMARY outcome. Monkeypatches
the dataset/backtest layers so the real wiring (which outcome_types
each variant requests, same coverage reused across all three) is
checked without touching the real DB."""

from __future__ import annotations

import datetime as dt

from ledgerlight.modelling import sensitivity
from ledgerlight.modelling.coverage import VerifiedCoverage


def _fake_coverage() -> VerifiedCoverage:
    return VerifiedCoverage(
        window_start=dt.date(2015, 1, 1),
        window_end=dt.date(2026, 1, 1),
        company_ids=[],
        company_names=[],
        ibbi_known_at_range=(dt.datetime(2015, 1, 1), dt.datetime(2026, 1, 1)),
        care_known_at_range=(dt.datetime(2015, 1, 1), dt.datetime(2026, 1, 1)),
    )


def test_each_variant_requests_the_right_outcome_types(monkeypatch) -> None:
    requested_outcome_types: list[list[str]] = []

    def fake_build_dataset(session, coverage, outcome_types=None):
        requested_outcome_types.append(outcome_types)
        return []

    def fake_run_backtest(rows, coverage, seed=42):
        return "fake-backtest-result"

    monkeypatch.setattr(sensitivity, "build_primary_outcome_dataset", fake_build_dataset)
    monkeypatch.setattr(sensitivity, "run_backtest", fake_run_backtest)

    coverage = _fake_coverage()
    result = sensitivity.run_sensitivity_analysis(session=None, coverage=coverage)

    assert requested_outcome_types[0] is None or set(requested_outcome_types[0]) == {
        "PRIMARY_IBBI_ADMISSION",
        "PRIMARY_RATING_DOWNGRADE_D",
    }
    assert requested_outcome_types[1] == sensitivity.RATING_DEFAULT_ONLY_OUTCOME_TYPES
    assert requested_outcome_types[2] == sensitivity.IBBI_ONLY_OUTCOME_TYPES
    assert result.primary == "fake-backtest-result"
    assert result.rating_default_only == "fake-backtest-result"
    assert result.ibbi_only == "fake-backtest-result"
