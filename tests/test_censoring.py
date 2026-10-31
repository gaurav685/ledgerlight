"""Tests for ledgerlight.modelling.censoring -- the real, code-level
enforcement of the two rules documented in docs/modelling/outcomes.md
§5. Each case is a concrete scenario, not just a smoke test: a company
still trading, a company that really disappeared early, and the plain
end-of-coverage case that applies to every company near the end of the
dataset."""

from __future__ import annotations

import datetime as dt

from ledgerlight.modelling.censoring import check_censoring


def test_not_censored_when_company_still_trading_and_window_fits() -> None:
    result = check_censoring(
        dt.date(2019, 1, 31),
        last_real_trade_date=dt.date(2026, 10, 30),
        data_coverage_end=dt.date(2026, 10, 30),
    )
    assert result.censored is False
    assert result.reason is None


def test_end_of_window_censored_near_the_end_of_real_coverage() -> None:
    """A company that is still actively trading right up to the end of
    coverage must still be censored if its forward window runs past
    that coverage end -- this is NOT a disappearance, just a real data
    boundary."""
    result = check_censoring(
        dt.date(2026, 6, 30),
        last_real_trade_date=dt.date(2026, 10, 30),
        data_coverage_end=dt.date(2026, 10, 30),
    )
    assert result.censored is True
    assert result.reason is not None
    assert result.reason.startswith("end_of_window_observation")


def test_a_company_still_trading_at_coverage_end_never_triggers_unknown_trading_stop() -> None:
    """Real regression guard: last_real_trade_date == data_coverage_end
    must never be read as "this company disappeared" just because it
    happens to be the most recent available data point."""
    result = check_censoring(
        dt.date(2020, 1, 31),
        last_real_trade_date=dt.date(2026, 10, 30),
        data_coverage_end=dt.date(2026, 10, 30),
    )
    assert result.censored is False


def test_unknown_trading_stop_for_a_real_early_disappearance() -> None:
    """A company whose real last trade was 2020-03-15, long before the
    real 2026-10-30 coverage end -- a genuine confirmed disappearance.
    An as_of whose forward window extends past the disappearance
    cutoff (2020-03-15 + 90d) must be censored for that specific reason."""
    result = check_censoring(
        dt.date(2020, 1, 31),
        last_real_trade_date=dt.date(2020, 3, 15),
        data_coverage_end=dt.date(2026, 10, 30),
    )
    assert result.censored is True
    assert result.reason is not None
    assert result.reason.startswith("unknown_trading_stop")


def test_not_censored_before_the_disappearance_cutoff_is_reached() -> None:
    """A company that later disappears (last trade 2020-03-15) but an
    as_of early enough that its own 12-month forward window ends
    BEFORE the disappearance cutoff -- not yet censored."""
    result = check_censoring(
        dt.date(2019, 1, 31),
        last_real_trade_date=dt.date(2020, 3, 15),
        data_coverage_end=dt.date(2026, 10, 30),
    )
    assert result.censored is False


def test_no_trade_history_at_all_falls_through_to_end_of_window_check() -> None:
    result = check_censoring(
        dt.date(2026, 6, 30),
        last_real_trade_date=None,
        data_coverage_end=dt.date(2026, 10, 30),
    )
    assert result.censored is True
    assert result.reason is not None
    assert result.reason.startswith("end_of_window_observation")
