"""Enhancement 1 Correction §1.2/§1.3: runs the real, empirically-
validated price-ratio corporate-action detector
(`ledgerlight.modelling.price_adjustment`) across every real EQ ISIN
in `price_bars`, persists detected factors (idempotent, append-only,
committed incrementally so a real interruption never loses already-
detected real work), and prints the real data-quality report the
brief's own §1.3 asks for: detected-action counts by year, and the
real residual suspicious jumps (large moves not matching any
plausible corporate-action ratio) for human review.

Memory-bounded by design (this host's own real memory instability is
a disclosed, recurring constraint this project works around
elsewhere): only a bounded top-N of residual jumps is kept in memory
at any time, never every real residual across ~3,800 ISINs.

Usage:
    python3 -m uv run python scripts/detect_price_adjustments.py [--apply]

Without --apply, prints what WOULD be inserted (a dry run).
"""

from __future__ import annotations

import argparse
import heapq
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import text  # noqa: E402

from ledgerlight.config.settings import load_settings  # noqa: E402
from ledgerlight.db.session import make_session_factory  # noqa: E402
from ledgerlight.modelling.price_adjustment import (  # noqa: E402
    all_real_eq_isins,
    detect_factors_for_isin,
    find_residual_suspicious_jumps,
    load_eq_closes_by_isin,
    persist_detected_factors,
)

COMMIT_EVERY_N_ISINS = 200
TOP_N_RESIDUALS_KEPT = 50


def main() -> int:
    parser = argparse.ArgumentParser(description="Detect real corporate-action price factors.")
    parser.add_argument("--apply", action="store_true", help="persist detected factors")
    args = parser.parse_args()

    settings = load_settings()
    session_factory = make_session_factory(settings)

    with session_factory() as session:
        trading_days = [
            row[0]
            for row in session.execute(
                text("SELECT DISTINCT trade_date FROM price_bars ORDER BY trade_date")
            ).all()
        ]
        print(f"real trading-day index: {len(trading_days)} days", flush=True)

        isins = all_real_eq_isins(session)
        print(f"real EQ ISINs to scan: {len(isins)}", flush=True)

        by_year: Counter[int] = Counter()
        total_detected = 0
        total_inserted = 0
        total_residuals = 0
        # (magnitude, tiebreaker, r) -- the tiebreaker is a strictly
        # increasing counter so two residuals with the exact same real
        # magnitude never fall through to comparing the dicts
        # themselves (dicts have no real ordering) -- a real bug found
        # running this against real data: two ties happened almost
        # immediately.
        top_residuals: list[tuple[float, int, dict[str, object]]] = []
        residual_counter = 0

        for i, (isin, symbol) in enumerate(isins):
            closes = load_eq_closes_by_isin(session, isin)
            if len(closes) >= 2:
                detected = detect_factors_for_isin(closes, trading_days, symbol, isin)
                for f in detected:
                    by_year[f.ex_date.year] += 1
                total_detected += len(detected)
                if args.apply and detected:
                    total_inserted += persist_detected_factors(session, detected)

                for r in find_residual_suspicious_jumps(closes, trading_days, symbol, isin):
                    total_residuals += 1
                    residual_counter += 1
                    magnitude = abs(float(r["ratio"]) - 1.0)  # type: ignore[arg-type]
                    entry = (magnitude, residual_counter, r)
                    if len(top_residuals) < TOP_N_RESIDUALS_KEPT:
                        heapq.heappush(top_residuals, entry)
                    elif magnitude > top_residuals[0][0]:
                        heapq.heapreplace(top_residuals, entry)

            if (i + 1) % COMMIT_EVERY_N_ISINS == 0:
                if args.apply:
                    session.commit()
                print(f"  ... {i + 1}/{len(isins)} ISINs scanned", flush=True)

        if args.apply:
            session.commit()

        print(f"\n--- real detected corporate-action factors: {total_detected} ---")
        print("by year:")
        for year in sorted(by_year):
            print(f"  {year}: {by_year[year]}")

        print(
            f"\n--- real residual suspicious jumps (no plausible ratio match): "
            f"{total_residuals} ---"
        )
        for _, _, r in sorted(top_residuals, key=lambda x: x[0], reverse=True):
            print(f"  {r}")
        if total_residuals > TOP_N_RESIDUALS_KEPT:
            print(
                f"  ... and {total_residuals - TOP_N_RESIDUALS_KEPT} more "
                f"(top {TOP_N_RESIDUALS_KEPT} by magnitude shown above)"
            )

        if args.apply:
            print(f"\n--- {total_inserted} new real price_adjustment_factors rows inserted ---")
        else:
            print(
                f"\n--- dry run: {total_detected} real factors would be inserted "
                "(pass --apply to commit) ---"
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
