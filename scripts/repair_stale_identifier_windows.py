"""One-time repair for a real bug found while building Phase 3 Sec4's
price-feature engine: each company's EARLIEST NSE_SYMBOL/ISIN
`company_identifiers` window has `valid_from` frozen at whatever
`scripts/bootstrap_companies.py` saw as that symbol/ISIN's first real
trade_date AT BOOTSTRAP TIME. Several bhavcopy backfills ran AFTER
bootstrap (the 2016-01-01..2017-01-04 parsing-pipeline gap fix, Sec2.1,
among others) and added real, earlier-dated price_bars rows -- but
bootstrap is deliberately idempotent (it skips any ISIN that already
has a company_identifiers row), so those earlier rows were never
reflected back into the identifier's own `valid_from`.

Real, measured impact (2026-10-31, found while joining price_bars to
company_id for feature-snapshot building): 1,484 of 3,764 real EQ
symbols (39%) and 1,452 ISINs have a `valid_from` LATER than their own
real earliest EQ trade_date, by up to 613 days. A naive point-in-time
join on these windows silently drops ~393,553 real EQ price_bars rows
(16.6% of the total) from company-keyed historical analysis -- not an
edge case.

SYMBOL-REUSE GUARD (user-mandated, 2026-10-31): a window is widened
only where every real price_bars row in the newly-covered period shares
the SAME (symbol, isin) pairing as the already-trusted period just
after it -- see `ledgerlight.ingestion.identifier_window_repair.
check_widen_guard`. A candidate failing this guard is skipped and
reported, never silently widened.

Every applied correction is written to the `identifier_window_corrections`
audit table (see its Alembic migration), not only to the pg_dump backup
taken before `--apply`.

--dry-run (default): writes a plan to
docs/phase-3/evidence/identifier-window-repair-dry-run.json, touches no
rows. --apply: performs the real update inside one transaction, then
verifies the real before/after effect and prints the raw SQL used.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import uuid
from pathlib import Path
from typing import Any, cast

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import CursorResult, text  # noqa: E402

from ledgerlight.config.settings import load_settings  # noqa: E402
from ledgerlight.db.session import make_session_factory  # noqa: E402
from ledgerlight.ingestion.identifier_window_repair import (  # noqa: E402
    TARGETS,
    check_widen_guard,
    find_stale_windows,
    load_price_bar_pairs,
    record_correction,
)

PLAN_PATH = REPO_ROOT / "docs" / "phase-3" / "evidence" / "identifier-window-repair-dry-run.json"
SCRIPT_NAME = "scripts/repair_stale_identifier_windows.py"

_JOIN_SQL = """
SELECT count(*) FROM price_bars pb
JOIN company_identifiers ci ON ci.identifier_type = 'NSE_SYMBOL' AND ci.value = pb.symbol
  AND pb.trade_date >= ci.valid_from AND (ci.valid_to IS NULL OR pb.trade_date <= ci.valid_to)
WHERE pb.series = 'EQ'
"""


def _build_plan(session: Any) -> dict[str, Any]:
    plan: dict[str, Any] = {"accepted": {}, "skipped": {}}
    for identifier_type, pb_column, _paired_column in TARGETS:
        pairs = load_price_bar_pairs(session, identifier_type)
        stale = find_stale_windows(session, identifier_type, pb_column)
        accepted = []
        skipped = []
        for row in stale:
            guard = check_widen_guard(pairs, row.value, row.recorded_valid_from)
            entry: dict[str, Any] = {
                "identifier_id": str(row.identifier_id),
                "value": row.value,
                "recorded_valid_from": row.recorded_valid_from.isoformat(),
                "real_earliest_trade": row.real_earliest_trade.isoformat(),
                "real_earliest_price_bar_id": (
                    str(row.real_earliest_price_bar_id)
                    if row.real_earliest_price_bar_id is not None
                    else None
                ),
                "days_stale": (row.recorded_valid_from - row.real_earliest_trade).days,
            }
            if guard.ok:
                accepted.append(entry)
            else:
                entry["guard_reason"] = guard.reason
                entry["distinct_paired_values"] = guard.distinct_paired_values
                entry["anchor_paired_value"] = guard.anchor_paired_value
                skipped.append(entry)
        plan["accepted"][identifier_type] = accepted
        plan["skipped"][identifier_type] = skipped
    return plan


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="perform the real update")
    args = parser.parse_args()

    settings = load_settings()
    session_factory = make_session_factory(settings)

    with session_factory() as session:
        plan = _build_plan(session)

    total_accepted = sum(len(v) for v in plan["accepted"].values())
    total_skipped = sum(len(v) for v in plan["skipped"].values())
    print(f"stale windows passing symbol-reuse guard (to widen): {total_accepted}")
    for identifier_type, rows in plan["accepted"].items():
        print(f"  {identifier_type}: {len(rows)}")
    print(f"stale windows FAILING symbol-reuse guard (skipped): {total_skipped}")
    for identifier_type, rows in plan["skipped"].items():
        print(f"  {identifier_type}: {len(rows)}")
        for row in rows[:10]:
            print(
                f"    SKIP {row['value']}: {row['guard_reason']} "
                f"(distinct_paired={row['distinct_paired_values']}, "
                f"anchor={row['anchor_paired_value']})"
            )

    if not args.apply:
        PLAN_PATH.parent.mkdir(parents=True, exist_ok=True)
        PLAN_PATH.write_text(json.dumps(plan, indent=2), encoding="utf-8")
        print(f"dry-run only -- plan written to {PLAN_PATH}")
        return 0

    with session_factory() as session:
        print("\n--- BEFORE ---")
        before_join_count = cast(int, session.execute(text(_JOIN_SQL)).scalar())
        print(f"EQ price_bars rows joinable to a company (NSE_SYMBOL window): {before_join_count}")
        sample_before = session.execute(
            text(
                "SELECT id, value, valid_from FROM company_identifiers "
                "WHERE id = ANY(:ids) ORDER BY value"
            ),
            {
                "ids": [
                    uuid.UUID(row["identifier_id"])
                    for row in (plan["accepted"]["NSE_SYMBOL"] + plan["accepted"]["ISIN"])[:10]
                ]
            },
        ).all()
        for row in sample_before:
            print(f"  BEFORE {row[1]}: valid_from={row[2]}")

        updated = 0
        narrowed = 0
        for identifier_type, _pb_column, _paired_column in TARGETS:
            for row in plan["accepted"][identifier_type]:
                old_valid_from = dt.date.fromisoformat(row["recorded_valid_from"])
                new_valid_from = dt.date.fromisoformat(row["real_earliest_trade"])
                if new_valid_from >= old_valid_from:
                    narrowed += 1  # should never happen -- guarded for below
                    continue
                result = session.execute(
                    text(
                        "UPDATE company_identifiers "
                        "SET valid_from = :new_valid_from, "
                        "source_price_bar_id = :new_price_bar_id "
                        "WHERE id = :identifier_id"
                    ),
                    {
                        "new_valid_from": new_valid_from,
                        "new_price_bar_id": (
                            uuid.UUID(row["real_earliest_price_bar_id"])
                            if row["real_earliest_price_bar_id"]
                            else None
                        ),
                        "identifier_id": uuid.UUID(row["identifier_id"]),
                    },
                )
                updated += cast("CursorResult[Any]", result).rowcount
                record_correction(
                    session,
                    identifier_id=uuid.UUID(row["identifier_id"]),
                    identifier_type=identifier_type,
                    value=row["value"],
                    old_valid_from=old_valid_from,
                    new_valid_from=new_valid_from,
                    reason="stale_window_repair_bootstrap_predates_backfill",
                    script_name=SCRIPT_NAME,
                )

        session.commit()

        print(f"\nupdated: {updated} company_identifiers rows")
        print(f"narrowed (should be 0): {narrowed}")
        assert narrowed == 0, "a window was narrowed -- this must never happen"
        assert updated == total_accepted, f"updated count {updated} != plan count {total_accepted}"

        print("\n--- AFTER ---")
        after_join_count = cast(int, session.execute(text(_JOIN_SQL)).scalar())
        print(f"EQ price_bars rows joinable to a company (NSE_SYMBOL window): {after_join_count}")
        print(f"recovered rows: {after_join_count - before_join_count}")

        sample_after = session.execute(
            text(
                "SELECT id, value, valid_from FROM company_identifiers "
                "WHERE id = ANY(:ids) ORDER BY value"
            ),
            {
                "ids": [
                    uuid.UUID(row["identifier_id"])
                    for row in (plan["accepted"]["NSE_SYMBOL"] + plan["accepted"]["ISIN"])[:10]
                ]
            },
        ).all()
        for row in sample_after:
            print(f"  AFTER  {row[1]}: valid_from={row[2]}")

        print("\n--- SQL used for verification ---")
        print(_JOIN_SQL)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
