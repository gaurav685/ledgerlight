"""Tests for scripts.compute_drawdown_threshold's pure helper functions
-- the ETF-pattern heuristic and median, which the real 2026-10-30 run
showed matter: without them, the computed threshold was contaminated by
real gold-ETF unit restructurings (~99% "drawdowns" that are not real
economic loss), not just hypothetically."""

from __future__ import annotations

import datetime as dt
import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
_SPEC = importlib.util.spec_from_file_location(
    "compute_drawdown_threshold", REPO_ROOT / "scripts" / "compute_drawdown_threshold.py"
)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules["compute_drawdown_threshold"] = _MODULE
_SPEC.loader.exec_module(_MODULE)


def test_looks_like_etf_catches_the_real_contaminating_symbols() -> None:
    for symbol in ("GOLDSHARE", "HDFCMFGETF", "BSLGOLDETF", "LIQUIDBEES"):
        assert _MODULE._looks_like_etf(symbol), symbol


def test_looks_like_etf_does_not_flag_an_ordinary_company() -> None:
    assert not _MODULE._looks_like_etf("INFY")
    assert not _MODULE._looks_like_etf("RELIANCE")


def test_nearest_within_finds_exact_and_nearby_dates() -> None:
    available = {dt.date(2020, 1, 10): 1.0, dt.date(2020, 1, 15): 2.0}
    assert _MODULE._nearest_within(dt.date(2020, 1, 10), available, 10) == dt.date(2020, 1, 10)
    assert _MODULE._nearest_within(dt.date(2020, 1, 12), available, 10) in (
        dt.date(2020, 1, 10),
        dt.date(2020, 1, 15),
    )


def test_nearest_within_returns_none_outside_tolerance() -> None:
    available = {dt.date(2020, 1, 10): 1.0}
    assert _MODULE._nearest_within(dt.date(2020, 2, 1), available, 5) is None


def test_month_end_dates_picks_the_latest_date_per_month() -> None:
    dates = {dt.date(2020, 1, 5), dt.date(2020, 1, 20), dt.date(2020, 2, 3)}
    assert _MODULE._month_end_dates(dates) == [dt.date(2020, 1, 20), dt.date(2020, 2, 3)]
