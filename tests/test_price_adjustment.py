"""Tests for ledgerlight.modelling.price_adjustment -- Enhancement 1
Correction §1. Pure unit tests against synthetic fixtures built to
mirror the real, empirically-verified behaviour documented in
docs/enhancements/event-study/evidence-sec1-corporate-action-verification.md
(the 5 real cited cases): `prev_close` is never touched by this
module at all -- only `close`, which is where the real adjustment
actually shows up."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from ledgerlight.modelling.price_adjustment import (
    adjusted_close,
    detect_factors_for_isin,
    find_residual_suspicious_jumps,
    match_plausible_ratio,
)


def _days(start: dt.date, n: int) -> list[dt.date]:
    out: list[dt.date] = []
    d = start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += dt.timedelta(days=1)
    return out


TRADING_DAYS = _days(dt.date(2024, 1, 1), 60)


def test_match_plausible_ratio_recognizes_a_11_bonus() -> None:
    # Real: Reliance 1:1 bonus, 2017-09-07, real factor 0.4972.
    assert match_plausible_ratio(0.4972) == "1:1 bonus"


def test_match_plausible_ratio_recognizes_a_13_bonus() -> None:
    # Real: Wipro 1:3 bonus, 2019-03-06, real factor 0.7631.
    assert match_plausible_ratio(0.7631) == "1:3 bonus"


def test_match_plausible_ratio_rejects_an_arbitrary_large_move() -> None:
    """The real false-positive guard: an ordinary big down day (e.g. a
    distressed stock's real -38% single-day crash) must not match any
    plausible ratio just because it's large."""
    assert match_plausible_ratio(0.69) is None


def test_detect_factors_for_isin_finds_a_real_split() -> None:
    """HDFC Bank's real 1:2 split: close(t-1)=2187.75 -> close(t)=1101.05
    (factor 0.5033), consecutive real sessions."""
    d0, d1 = TRADING_DAYS[10], TRADING_DAYS[11]
    closes = {d0: Decimal("2187.7500"), d1: Decimal("1101.0500")}
    detected = detect_factors_for_isin(closes, TRADING_DAYS, "HDFCBANK", "INE040A01034")
    assert len(detected) == 1
    assert detected[0].ex_date == d1
    assert detected[0].matched_ratio_label in ("1:1 bonus", "1:2 split")


def test_detect_factors_for_isin_finds_a_real_bonus() -> None:
    """TCS's real 1:1 bonus: close(t-1)=3514.10 -> close(t)=1741.05
    (factor 0.4954)."""
    d0, d1 = TRADING_DAYS[20], TRADING_DAYS[21]
    closes = {d0: Decimal("3514.1000"), d1: Decimal("1741.0500")}
    detected = detect_factors_for_isin(closes, TRADING_DAYS, "TCS", "INE467B01029")
    assert len(detected) == 1
    assert detected[0].factor == Decimal(str(float(Decimal("1741.0500") / Decimal("3514.1000"))))


def test_detect_factors_for_isin_no_false_positive_on_an_ordinary_crash() -> None:
    """A real, large, but NOT ratio-matching move (e.g. a circuit-limit
    sequence or a distressed-stock crash) must not be detected as a
    corporate action."""
    d0, d1 = TRADING_DAYS[5], TRADING_DAYS[6]
    closes = {d0: Decimal("100.00"), d1: Decimal("69.00")}  # -31%, matches no plausible ratio
    detected = detect_factors_for_isin(closes, TRADING_DAYS, "DISTRESSED", "INE000X00000")
    assert detected == []


def test_detect_factors_for_isin_ignores_moves_across_a_real_trading_gap() -> None:
    """Two REAL price rows that are not on consecutive real trading
    days (a real illiquidity gap) must never be compared -- the move
    could be ordinary price drift over the missed sessions, not a
    corporate action."""
    d0 = TRADING_DAYS[0]
    d_gap = TRADING_DAYS[15]  # far apart, real gap
    closes = {d0: Decimal("100.00"), d_gap: Decimal("50.00")}  # would match "1:1 bonus" if compared
    detected = detect_factors_for_isin(closes, TRADING_DAYS, "THIN", "INE000Y00000")
    assert detected == []


def test_detect_factors_for_isin_ignores_a_sparse_global_index_gap() -> None:
    """Real bug found during the §1.2 rerun: when the GLOBAL trading-day
    index itself is sparse (this project's own real 2020-2024 twice-
    monthly ingestion gap, see docs/ingestion/runbook.md), two snapshot
    dates ~15 real calendar days apart can be "adjacent" in that sparse
    index even though no other real trading day exists between them
    anywhere in price_bars. A real calendar-day bound must reject this
    too, not just the per-ISIN-only gap covered above."""
    # only these two dates exist at all in the global index
    sparse_trading_days = [dt.date(2020, 3, 20), dt.date(2020, 4, 20)]
    closes = {sparse_trading_days[0]: Decimal("100.00"), sparse_trading_days[1]: Decimal("50.00")}
    detected = detect_factors_for_isin(closes, sparse_trading_days, "SPARSEYR", "INE000V00000")
    assert detected == []


def test_detect_factors_for_isin_no_false_positive_on_ordinary_moves() -> None:
    """A real, small, everyday price move (well under the 15% real
    minimum) must never be flagged."""
    d0, d1 = TRADING_DAYS[0], TRADING_DAYS[1]
    closes = {d0: Decimal("100.00"), d1: Decimal("94.00")}  # -6%, ordinary
    detected = detect_factors_for_isin(closes, TRADING_DAYS, "ORDINARY", "INE000Z00000")
    assert detected == []


def test_find_residual_suspicious_jumps_reports_unmatched_large_moves() -> None:
    d0, d1 = TRADING_DAYS[0], TRADING_DAYS[1]
    closes = {d0: Decimal("100.00"), d1: Decimal("69.00")}
    residuals = find_residual_suspicious_jumps(
        closes, TRADING_DAYS, "DISTRESSED", "INE000X00000", threshold=0.25
    )
    assert len(residuals) == 1
    assert residuals[0]["ratio"] == 0.69


def test_find_residual_suspicious_jumps_does_not_report_a_real_matched_action() -> None:
    d0, d1 = TRADING_DAYS[0], TRADING_DAYS[1]
    closes = {d0: Decimal("100.00"), d1: Decimal("50.00")}  # a real 1:1-bonus-shaped move
    residuals = find_residual_suspicious_jumps(closes, TRADING_DAYS, "BONUSCO", "INE000W00000")
    assert residuals == []


# --- point-in-time adjusted_close --------------------------------------------


def test_adjusted_close_applies_a_known_factor_to_a_prior_price() -> None:
    ex_date = dt.date(2020, 6, 1)
    prior_date = dt.date(2020, 5, 1)
    factors = [(ex_date, Decimal("0.5"))]
    raw = Decimal("200.00")
    assert adjusted_close(raw, prior_date, factors) == Decimal("100.000")


def test_adjusted_close_does_not_adjust_a_price_on_or_after_ex_date() -> None:
    ex_date = dt.date(2020, 6, 1)
    factors = [(ex_date, Decimal("0.5"))]
    raw = Decimal("100.00")
    assert adjusted_close(raw, ex_date, factors) == raw
    assert adjusted_close(raw, ex_date + dt.timedelta(days=1), factors) == raw


def test_adjusted_close_point_in_time_a_future_factor_is_never_applied() -> None:
    """The real point-in-time rule: `adjusted_close` only ever applies
    whatever factors the CALLER passes in -- a factor list already
    scoped to `ex_date <= as_of` (by `get_adjustment_factors`) means a
    future corporate action is simply never in the list at all, so a
    historical price as of a past as_of is never retroactively
    adjusted for a split that hadn't happened yet."""
    raw = Decimal("200.00")
    prior_date = dt.date(2020, 1, 1)
    # Simulates calling as_of = 2020-05-01, BEFORE the real 2020-06-01
    # ex_date -- get_adjustment_factors would return an empty list here.
    factors_known_as_of_may: list[tuple[dt.date, Decimal]] = []
    assert adjusted_close(raw, prior_date, factors_known_as_of_may) == raw


def test_adjusted_close_applies_multiple_real_factors_cumulatively() -> None:
    """A real price before TWO later real corporate actions is
    adjusted by both, multiplicatively -- e.g. Bajaj Finance's real
    combined 4:1 bonus (factor 1/5) + 1:2 split (factor 1/2), total
    1/10."""
    factors = [
        (dt.date(2024, 6, 16), Decimal("0.2")),  # 4:1 bonus component
        (dt.date(2024, 6, 17), Decimal("0.5")),  # 1:2 split component
    ]
    raw = Decimal("1000.00")
    result = adjusted_close(raw, dt.date(2024, 1, 1), factors)
    assert result == Decimal("100.000")  # 1000 * 0.2 * 0.5
