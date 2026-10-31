"""Tests for ledgerlight.modelling.survivorship.identify_delisted_companies
-- the real >= 90-day-gap rule, same threshold as censoring.py's
unknown_trading_stop. Uses a fake session (no real DB) so the
pure date-arithmetic logic is pinned directly."""

from __future__ import annotations

import datetime as dt
import uuid

from ledgerlight.modelling.coverage import VerifiedCoverage
from ledgerlight.modelling.survivorship import identify_delisted_companies

COMPANY_A = uuid.uuid4()
COMPANY_B = uuid.uuid4()


class _FakeResult:
    def __init__(self, value):
        self._value = value

    def scalar(self):
        return self._value


class _FakeSession:
    """Returns the fixed coverage-end date for the single real query
    this module issues; `load_last_real_trade_dates` is monkeypatched
    separately in the test itself since it needs a real SQL row shape."""

    def __init__(self, coverage_end: dt.date):
        self.coverage_end = coverage_end

    def execute(self, *_args, **_kwargs):
        return _FakeResult(self.coverage_end)


def _coverage() -> VerifiedCoverage:
    return VerifiedCoverage(
        window_start=dt.date(2015, 1, 1),
        window_end=dt.date(2026, 1, 1),
        company_ids=[COMPANY_A, COMPANY_B],
        company_names=["A", "B"],
        ibbi_known_at_range=(dt.datetime(2015, 1, 1), dt.datetime(2026, 1, 1)),
        care_known_at_range=(dt.datetime(2015, 1, 1), dt.datetime(2026, 1, 1)),
    )


def test_a_company_with_a_real_90_day_plus_gap_is_flagged_delisted(monkeypatch) -> None:
    coverage_end = dt.date(2026, 10, 30)
    session = _FakeSession(coverage_end)

    def fake_last_trade_dates(_session, _company_ids):
        return {COMPANY_A: dt.date(2026, 1, 1), COMPANY_B: dt.date(2026, 10, 25)}

    monkeypatch.setattr(
        "ledgerlight.modelling.survivorship.load_last_real_trade_dates", fake_last_trade_dates
    )
    delisted = identify_delisted_companies(session, _coverage())
    assert delisted == {COMPANY_A: "A"}


def test_a_company_still_trading_at_coverage_end_is_never_flagged(monkeypatch) -> None:
    coverage_end = dt.date(2026, 10, 30)
    session = _FakeSession(coverage_end)

    def fake_last_trade_dates(_session, _company_ids):
        return {COMPANY_A: coverage_end, COMPANY_B: coverage_end}

    monkeypatch.setattr(
        "ledgerlight.modelling.survivorship.load_last_real_trade_dates", fake_last_trade_dates
    )
    assert identify_delisted_companies(session, _coverage()) == {}


def test_a_company_with_no_real_trade_history_is_skipped_not_flagged(monkeypatch) -> None:
    coverage_end = dt.date(2026, 10, 30)
    session = _FakeSession(coverage_end)

    def fake_last_trade_dates(_session, _company_ids):
        return {COMPANY_A: coverage_end}

    monkeypatch.setattr(
        "ledgerlight.modelling.survivorship.load_last_real_trade_dates", fake_last_trade_dates
    )
    assert identify_delisted_companies(session, _coverage()) == {}
