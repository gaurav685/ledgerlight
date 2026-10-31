"""Shared logic for widening a stale `company_identifiers` window (never
narrowing one) when real, earlier price_bars evidence exists than what
was recorded at bootstrap time. Used by both
`scripts/repair_stale_identifier_windows.py` (one-time repair of the
real bug found while building Phase 3 Sec4's price-feature engine --
bootstrap is idempotent, so identifiers bootstrapped before a later
bhavcopy backfill filled in earlier history never got corrected) and
`scripts/bootstrap_companies.py` (the root-cause fix: widen on re-run
instead of staying silently stale forever).

SYMBOL-REUSE GUARD: a window is only widened when every real price_bars
row in the newly-covered period shares the SAME (symbol, isin) pairing
as the already-trusted period just after it. This rejects widening
across a genuine symbol reuse (a different real company that happened
to trade under the same NSE symbol or, in principle, share an ISIN,
years apart) -- see `check_widen_guard`.

Every applied correction is written to `identifier_window_corrections`
(see the Alembic migration that creates it) -- the audit trail is a
real database table, not just a log file or a pg_dump backup.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections import defaultdict
from dataclasses import dataclass
from typing import cast

from sqlalchemy import text
from sqlalchemy.orm import Session

# own_value -> sorted list of (trade_date, paired_value), e.g. for
# identifier_type="NSE_SYMBOL" this maps a symbol to its (date, isin) history.
PriceBarPairs = dict[str, list[tuple[dt.date, str]]]

SCRIPT_VERSION = "2.0"

# (identifier_type, price_bars column keyed on this identifier's own value,
#  price_bars column that must stay consistent across the widened period)
TARGETS: list[tuple[str, str, str]] = [
    ("NSE_SYMBOL", "symbol", "isin"),
    ("ISIN", "isin", "symbol"),
]


@dataclass
class StaleWindow:
    identifier_id: uuid.UUID
    identifier_type: str
    value: str
    recorded_valid_from: dt.date
    real_earliest_trade: dt.date
    real_earliest_price_bar_id: uuid.UUID | None


@dataclass
class GuardResult:
    ok: bool
    reason: str
    distinct_paired_values: list[str]
    anchor_paired_value: str | None


def find_stale_windows(session: Session, identifier_type: str, pb_column: str) -> list[StaleWindow]:
    """Earliest-per-value window whose recorded valid_from is later than
    the real earliest EQ trade_date for that value. Uses a single
    DISTINCT ON pass over price_bars rather than a per-group correlated
    subquery -- the latter is catastrophically slow for `isin`, which has
    no index."""
    sql = text(
        f"""
        WITH real_earliest AS (
            SELECT DISTINCT ON ({pb_column}) {pb_column} AS value,
                   trade_date AS real_earliest_trade,
                   id AS real_earliest_price_bar_id
            FROM price_bars
            WHERE series = 'EQ' AND {pb_column} IS NOT NULL AND {pb_column} <> ''
            ORDER BY {pb_column}, trade_date ASC
        ),
        earliest_window AS (
            SELECT DISTINCT ON (value) id, value, valid_from AS recorded_valid_from
            FROM company_identifiers
            WHERE identifier_type = :identifier_type
            ORDER BY value, valid_from ASC
        )
        SELECT ew.id, ew.value, ew.recorded_valid_from, re.real_earliest_trade,
               re.real_earliest_price_bar_id
        FROM earliest_window ew
        JOIN real_earliest re ON re.value = ew.value
        WHERE re.real_earliest_trade < ew.recorded_valid_from
        ORDER BY ew.value
        """
    )
    rows = session.execute(sql, {"identifier_type": identifier_type}).all()
    return [
        StaleWindow(
            identifier_id=row[0],
            identifier_type=identifier_type,
            value=row[1],
            recorded_valid_from=row[2],
            real_earliest_trade=row[3],
            real_earliest_price_bar_id=row[4],
        )
        for row in rows
    ]


def load_price_bar_pairs(session: Session, identifier_type: str) -> PriceBarPairs:
    """One bulk fetch of (own_value, trade_date, paired_value) for every
    real EQ price_bars row -- used to check the symbol-reuse guard for
    every candidate in memory, instead of one unindexed SQL scan per
    ISIN (price_bars has no index on `isin`)."""
    own_col, paired_col = (
        ("symbol", "isin") if identifier_type == "NSE_SYMBOL" else ("isin", "symbol")
    )
    rows = session.execute(
        text(
            f"SELECT {own_col}, trade_date, {paired_col} FROM price_bars "
            f"WHERE series = 'EQ' AND {paired_col} IS NOT NULL AND {paired_col} <> ''"
        )
    ).all()
    pairs: PriceBarPairs = defaultdict(list)
    for row in rows:
        own_value, trade_date, paired_value = (
            cast(str, row[0]),
            cast(dt.date, row[1]),
            cast(str, row[2]),
        )
        pairs[own_value].append((trade_date, paired_value))
    for own_value in pairs:
        pairs[own_value].sort(key=lambda pair: pair[0])
    return pairs


def check_widen_guard(pairs: PriceBarPairs, value: str, gap_end_exclusive: dt.date) -> GuardResult:
    """Real guard: every price_bars row for `value` strictly before
    `gap_end_exclusive` (the newly-covered period) must share the same
    paired (symbol, isin) value as the row(s) at or after it (the
    already-trusted period). If the paired value differs or is
    ambiguous, this is a real or possible symbol/ISIN reuse -- skip."""
    history = pairs.get(value, [])
    anchor_values = [paired for trade_date, paired in history if trade_date >= gap_end_exclusive]
    if not anchor_values:
        return GuardResult(False, "no_anchor_data_at_or_after_recorded_valid_from", [], None)
    anchor_paired_value = anchor_values[0]

    gap_values = [paired for trade_date, paired in history if trade_date < gap_end_exclusive]
    if not gap_values:
        return GuardResult(False, "no_gap_rows_found", [], anchor_paired_value)

    distinct_paired = sorted(set(gap_values))
    if len(distinct_paired) > 1:
        return GuardResult(
            False,
            "symbol_reuse_multiple_paired_values_in_gap",
            distinct_paired,
            anchor_paired_value,
        )
    if distinct_paired[0] != anchor_paired_value:
        return GuardResult(
            False, "symbol_reuse_paired_value_mismatch", distinct_paired, anchor_paired_value
        )
    return GuardResult(True, "ok", distinct_paired, anchor_paired_value)


def record_correction(
    session: Session,
    *,
    identifier_id: uuid.UUID,
    identifier_type: str,
    value: str,
    old_valid_from: dt.date,
    new_valid_from: dt.date,
    reason: str,
    script_name: str,
) -> None:
    session.execute(
        text(
            "INSERT INTO identifier_window_corrections "
            "(id, identifier_id, identifier_type, value, old_valid_from, new_valid_from, "
            " reason, script_name, script_version, applied_at) "
            "VALUES (:id, :identifier_id, :identifier_type, :value, :old_valid_from, "
            " :new_valid_from, :reason, :script_name, :script_version, now())"
        ),
        {
            "id": uuid.uuid4(),
            "identifier_id": identifier_id,
            "identifier_type": identifier_type,
            "value": value,
            "old_valid_from": old_valid_from,
            "new_valid_from": new_valid_from,
            "reason": reason,
            "script_name": script_name,
            "script_version": SCRIPT_VERSION,
        },
    )
