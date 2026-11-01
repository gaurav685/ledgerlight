"""Phase 4 §10 `agent-eval` command: runs the real evaluation
(`ledgerlight.agent.eval.run_evaluation`) across the real SEED-track
(15 companies) and the real, query-derived UNIVERSE-track (~15
companies), and prints the real report."""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from ledgerlight.agent.eval import (  # noqa: E402
    DEFAULT_EVAL_AS_OF_DATES,
    print_eval_report,
    run_evaluation,
)
from ledgerlight.config.settings import load_settings  # noqa: E402
from ledgerlight.db.session import make_session_factory  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the real Sec8 agent evaluation.")
    parser.add_argument(
        "--as-of",
        action="append",
        default=None,
        help="repeatable: YYYY-MM-DD (default: the two real built-in dates)",
    )
    parser.add_argument("--requested-by", default="agent-eval")
    args = parser.parse_args()

    as_of_dates = (
        tuple(dt.date.fromisoformat(s) for s in args.as_of)
        if args.as_of
        else DEFAULT_EVAL_AS_OF_DATES
    )

    settings = load_settings()
    session_factory = make_session_factory(settings)

    with session_factory() as session:
        report = run_evaluation(session, as_of_dates=as_of_dates, requested_by=args.requested_by)

    print_eval_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
