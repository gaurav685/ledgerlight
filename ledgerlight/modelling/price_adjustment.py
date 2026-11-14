"""Enhancement 1 Correction §1: real corporate-action price adjustment.

Empirically verified (see
`docs/enhancements/event-study/evidence-sec1-corporate-action-verification.md`)
against 5 real, independently cited public stock splits/bonuses plus a
real negative control (a company with no corporate action ever) before
writing a single line of detection code here, per the brief's own "do
not guess factors" requirement:

- The bhavcopy's own `prev_close` field does NOT reflect adjustments --
  on all 5 real cases it is exactly the real prior session's raw
  `close`, unadjusted. The brief's own suggested
  `prev_close(t) / close(t-1)` detector does not work on this data,
  confirmed empirically, not assumed.
- The real adjustment shows up entirely in `close` itself, as a clean
  single-day, consecutive-session drop/jump matching the real
  corporate action's own economic ratio (to within ordinary daily
  price-movement noise).

So the real, validated detector here looks for a large, clean,
consecutive-session `close(t)/close(t-1)` ratio that matches one of a
small, enumerable set of economically plausible corporate-action
ratios -- never "any large move", which would conflate a real split
with an ordinary distressed-stock crash or circuit-limit sequence (a
real false-positive risk, checked directly in
`tests/test_price_adjustment.py`).

Raw `price_bars` is never mutated. Point-in-time correctness: a
factor is only ever applied to a price dated strictly BEFORE its own
`ex_date`, and only when that `ex_date` is itself known (<=) as of the
caller's own `as_of` -- a feature computed as of a date before some
later real corporate action never reflects that future action.
"""

from __future__ import annotations

import datetime as dt
import json
import uuid
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
from typing import cast

from sqlalchemy import text
from sqlalchemy.orm import Session

# Economically plausible real corporate-action ratios, as a curated,
# deliberately SPARSE (label, Fraction) list -- a detected factor is
# only ever accepted if it is close to one of these NAMED,
# real-world-practiced ratios, never "any large move" and never a
# densely-generated mathematical grid. A first version of this table
# generated every (new, held) pair for new/held in 1..10 and was
# found, while writing tests/test_price_adjustment.py, to pack the
# whole [0,1] interval densely enough that an arbitrary -38% crash
# matched "5:8 bonus" (a ratio no real company has ever actually
# used) -- exactly the false-positive risk this table exists to
# avoid. Covers the real cases in the evidence doc (1:1 bonus -> 1/2,
# 1:2 split -> 1/2, 1:3 bonus -> 3/4) plus the standard range of real
# Indian bonus/split ratios, including a combined bonus+split (e.g.
# Bajaj Finance's real 4:1 bonus + 1:2 split -> 1/10).
_BONUS_RATIOS: list[tuple[int, int]] = [  # (new shares, shares held)
    (1, 1),
    (1, 2),
    (1, 3),
    (1, 4),
    (1, 5),
    (1, 10),
    (2, 1),
    (2, 3),
    (2, 5),
    (3, 1),
    (3, 2),
    (3, 4),
    (3, 5),
    (4, 1),
    (4, 5),
    (5, 1),
    (5, 2),
    (5, 4),
    (9, 10),
    (10, 1),
]
_SPLIT_N: list[int] = [2, 3, 4, 5, 6, 10, 20]  # 1 old share -> n new shares
_COMBINED_BONUS_PLUS_SPLIT: list[tuple[int, int]] = [  # real multi-action combos
    (4, 2),  # Bajaj Finance real 4:1 bonus + 1:2 split -> total 10x shares
    (3, 2),
    (4, 5),
]

_PLAUSIBLE_RATIOS: list[tuple[str, Fraction]] = []
for _new, _held in _BONUS_RATIOS:
    _PLAUSIBLE_RATIOS.append((f"{_new}:{_held} bonus", Fraction(_held, _held + _new)))
for _n in _SPLIT_N:
    _PLAUSIBLE_RATIOS.append((f"1:{_n} split", Fraction(1, _n)))
    _PLAUSIBLE_RATIOS.append((f"{_n}:1 reverse split", Fraction(_n, 1)))
for _bonus_new, _split_n in _COMBINED_BONUS_PLUS_SPLIT:
    _total_multiple = (1 + _bonus_new) * _split_n
    _PLAUSIBLE_RATIOS.append(
        (f"{_bonus_new}:1 bonus + 1:{_split_n} split (combined)", Fraction(1, _total_multiple))
    )
# De-duplicate by fraction value, keeping the first (shortest/simplest) label.
_seen: set[Fraction] = set()
_DEDUPED_RATIOS: list[tuple[str, Fraction]] = []
for _label, _frac in _PLAUSIBLE_RATIOS:
    if _frac not in _seen:
        _seen.add(_frac)
        _DEDUPED_RATIOS.append((_label, _frac))
PLAUSIBLE_RATIOS: tuple[tuple[str, Fraction], ...] = tuple(_DEDUPED_RATIOS)

MIN_ABS_RETURN_TO_CONSIDER = 0.15  # a real candidate must move >= 15%
# 3%, not tighter: the real cited cases include genuine same-day market
# movement layered on top of the structural ratio (e.g. Infosys's real
# 2018-09-04 bonus day ratio is 2.8% off the exact 1:1 structural 0.5 --
# an ordinary daily move, not a detection error) -- confirmed against
# all 5 real cases in the evidence doc before choosing this value.
RATIO_MATCH_TOLERANCE = 0.03


@dataclass
class DetectedFactor:
    isin: str
    symbol: str
    ex_date: dt.date
    prior_date: dt.date
    prior_close: Decimal
    new_close: Decimal
    factor: Decimal
    matched_ratio_label: str


def match_plausible_ratio(factor: float) -> str | None:
    """Returns the real, human-readable label of the closest plausible
    corporate-action ratio if `factor` is within `RATIO_MATCH_TOLERANCE`
    of one, else None. Never accepts an arbitrary large move -- this is
    exactly the real false-positive guard (circuit-limit crashes, a
    distressed stock's ordinary huge-volatility day) the brief's own
    §1.3 asks to be checked."""
    best_label: str | None = None
    best_distance = RATIO_MATCH_TOLERANCE
    for label, frac in PLAUSIBLE_RATIOS:
        target = float(frac)
        if target == 0:
            continue
        relative_distance = abs(factor - target) / target
        if relative_distance <= best_distance:
            best_distance = relative_distance
            best_label = label
    return best_label


# Real, found-during-§1.2-rerun bug: `price_bars` itself has non-uniform
# ingestion density across its real history (docs/ingestion/runbook.md --
# the Phase 0 seed only sampled bhavcopy twice a month; Phase 1's daily
# backfill was only ever run for part of the range). For 2020-2024
# specifically, the GLOBAL trading-day index built from `price_bars` is
# ITSELF only ~2 dates/month, so "adjacent in that index" does not mean
# "one real trading session apart" -- it can mean ~15 real calendar days
# apart. A real calendar-day bound is required in addition to index
# adjacency, or two snapshot dates ~15 days apart get treated as a single
# session and real ordinary drift over 2 weeks gets misread as a
# corporate-action-sized jump.
MAX_REAL_CALENDAR_GAP_DAYS = 5  # covers an ordinary weekend + 1-2 holidays


def _consecutive_session_pairs(
    closes_by_date: dict[dt.date, Decimal], trading_days: list[dt.date]
) -> list[tuple[dt.date, dt.date]]:
    """Real (prior_day, day) pairs that are genuinely adjacent in the
    GLOBAL real trading-day index AND no more than
    `MAX_REAL_CALENDAR_GAP_DAYS` real calendar days apart -- never
    merely "the next date this one ISIN happens to have a close for"
    (a real bug found and fixed while writing
    tests/test_price_adjustment.py's own gap test), and never merely
    "the next date anything in price_bars happens to have a row for"
    either, since that global index can itself be sparse over a real
    stretch of this project's own ingestion history (a second real
    bug, found while reviewing the real §1.2 detection run's output:
    the 2020-2024 sparse-ingestion years accounted for the large
    majority of "detections", most of them really 15-day-apart
    snapshot pairs misread as single sessions)."""
    day_index = {d: i for i, d in enumerate(trading_days)}
    available_days = sorted(d for d in trading_days if d in closes_by_date)
    pairs: list[tuple[dt.date, dt.date]] = []
    for prior_day, day in zip(available_days, available_days[1:], strict=False):
        if day_index[day] - day_index[prior_day] != 1:
            continue
        if (day - prior_day).days > MAX_REAL_CALENDAR_GAP_DAYS:
            continue
        pairs.append((prior_day, day))
    return pairs


def detect_factors_for_isin(
    closes_by_date: dict[dt.date, Decimal], trading_days: list[dt.date], symbol: str, isin: str
) -> list[DetectedFactor]:
    """Pure detection over one real ISIN's own real EQ closes, along
    the real trading-day index (so a multi-week illiquidity gap is
    never mistaken for a corporate action -- only genuinely
    consecutive real sessions are compared)."""
    detected: list[DetectedFactor] = []
    for prior_day, day in _consecutive_session_pairs(closes_by_date, trading_days):
        prior_close = closes_by_date[prior_day]
        new_close = closes_by_date[day]
        if prior_close == 0:
            continue
        ratio = float(new_close / prior_close)
        if abs(ratio - 1.0) < MIN_ABS_RETURN_TO_CONSIDER:
            continue
        label = match_plausible_ratio(ratio)
        if label is None:
            continue
        detected.append(
            DetectedFactor(
                isin=isin,
                symbol=symbol,
                ex_date=day,
                prior_date=prior_day,
                prior_close=prior_close,
                new_close=new_close,
                factor=Decimal(str(ratio)),
                matched_ratio_label=label,
            )
        )
    return detected


def find_residual_suspicious_jumps(
    closes_by_date: dict[dt.date, Decimal],
    trading_days: list[dt.date],
    symbol: str,
    isin: str,
    threshold: float = 0.40,
) -> list[dict[str, object]]:
    """Real consecutive-session jumps >= `threshold` that did NOT match
    any plausible corporate-action ratio -- reported for human review
    (brief §1.3), never silently folded into the real adjustment
    table."""
    residual: list[dict[str, object]] = []
    for prior_day, day in _consecutive_session_pairs(closes_by_date, trading_days):
        prior_close = closes_by_date[prior_day]
        new_close = closes_by_date[day]
        if prior_close == 0:
            continue
        ratio = float(new_close / prior_close)
        if abs(ratio - 1.0) < threshold:
            continue
        if match_plausible_ratio(ratio) is not None:
            continue
        residual.append(
            {
                "isin": isin,
                "symbol": symbol,
                "date": day,
                "prior_date": prior_day,
                "prior_close": float(prior_close),
                "new_close": float(new_close),
                "ratio": ratio,
            }
        )
    return residual


# --- DB-touching layer -------------------------------------------------------


def load_eq_closes_by_isin(session: Session, isin: str) -> dict[dt.date, Decimal]:
    rows = session.execute(
        text(
            "SELECT trade_date, close FROM price_bars "
            "WHERE isin = :isin AND series = 'EQ' AND close IS NOT NULL "
            "ORDER BY trade_date"
        ),
        {"isin": isin},
    ).all()
    return {cast(dt.date, r[0]): cast(Decimal, r[1]) for r in rows}


def all_real_eq_isins(session: Session) -> list[tuple[str, str]]:
    """Every real (isin, a representative symbol) pair with EQ price
    history -- the real universe this detector runs over."""
    rows = session.execute(
        text(
            "SELECT isin, (array_agg(symbol ORDER BY trade_date DESC))[1] AS latest_symbol "
            "FROM price_bars WHERE series = 'EQ' AND isin IS NOT NULL "
            "GROUP BY isin"
        )
    ).all()
    return [(cast(str, r[0]), cast(str, r[1])) for r in rows]


def persist_detected_factors(session: Session, factors: list[DetectedFactor]) -> int:
    """Idempotent, append-only-in-spirit: a (isin, ex_date) pair already
    recorded is skipped, never duplicated or overwritten -- consistent
    with this project's own standing backfill-script convention."""
    inserted = 0
    for f in factors:
        existing = session.execute(
            text(
                "SELECT 1 FROM price_adjustment_factors WHERE isin = :isin AND ex_date = :ex_date"
            ),
            {"isin": f.isin, "ex_date": f.ex_date},
        ).first()
        if existing is not None:
            continue
        session.execute(
            text(
                "INSERT INTO price_adjustment_factors "
                "(id, isin, symbol, ex_date, factor, method, evidence_json) "
                "VALUES (:id, :isin, :symbol, :ex_date, :factor, :method, CAST(:evidence AS JSONB))"
            ),
            {
                "id": uuid.uuid4(),
                "isin": f.isin,
                "symbol": f.symbol,
                "ex_date": f.ex_date,
                "factor": f.factor,
                "method": "price_ratio_detected",
                "evidence": json.dumps(
                    {
                        "prior_date": f.prior_date.isoformat(),
                        "prior_close": str(f.prior_close),
                        "new_date": f.ex_date.isoformat(),
                        "new_close": str(f.new_close),
                        "matched_ratio_label": f.matched_ratio_label,
                    }
                ),
            },
        )
        inserted += 1
    return inserted


def get_adjustment_factors(
    session: Session, isin: str, as_of: dt.date
) -> list[tuple[dt.date, Decimal]]:
    """Every real adjustment factor for this ISIN with `ex_date <=
    as_of` -- the point-in-time rule: a factor dated after `as_of` is
    not yet known as of that date and is never applied."""
    rows = session.execute(
        text(
            "SELECT ex_date, factor FROM price_adjustment_factors "
            "WHERE isin = :isin AND ex_date <= :as_of ORDER BY ex_date"
        ),
        {"isin": isin, "as_of": as_of},
    ).all()
    return [(cast(dt.date, r[0]), cast(Decimal, r[1])) for r in rows]


def adjusted_close(
    raw_close: Decimal, trade_date: dt.date, factors_known_as_of: list[tuple[dt.date, Decimal]]
) -> Decimal:
    """Real backward adjustment: a raw close dated strictly before a
    real factor's own `ex_date` is multiplied by that factor (bringing
    it onto the post-action scale); a close on or after `ex_date` is
    already on that scale and is left alone for that factor. Only
    factors already passed in as `factors_known_as_of` (the caller's
    own point-in-time-scoped list, see `get_adjustment_factors`) are
    ever applied -- this function itself has no notion of "today"."""
    result = raw_close
    for ex_date, factor in factors_known_as_of:
        if trade_date < ex_date:
            result = result * factor
    return result


def get_adjusted_closes(session: Session, isin: str, as_of: dt.date) -> dict[dt.date, Decimal]:
    """The real, point-in-time-correct adjusted close series for one
    ISIN, as of `as_of` -- raw `price_bars` is read, never mutated;
    this is a pure computed view over it."""
    raw_closes = load_eq_closes_by_isin(session, isin)
    factors = get_adjustment_factors(session, isin, as_of)
    if not factors:
        return {d: c for d, c in raw_closes.items() if d <= as_of}
    return {d: adjusted_close(c, d, factors) for d, c in raw_closes.items() if d <= as_of}
