"""Phase 4 §10 `investigate-batch` command: runs real investigations
across a real set of (company, as_of) targets -- an explicit list of
`--company`, and/or the real SEED-track and UNIVERSE-track selections
from `ledgerlight.agent.eval`. One line of real output per run; no
aggregated statistics (that is `agent-eval`'s own job)."""

from __future__ import annotations

import argparse
import datetime as dt
import sys
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from ledgerlight.agent.eval import (  # noqa: E402
    seed_track_company_ids,
    universe_track_company_ids,
)
from ledgerlight.agent.state_machine import run_investigation  # noqa: E402
from ledgerlight.config.settings import load_settings  # noqa: E402
from ledgerlight.db.session import make_session_factory  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run real investigations over a real batch.")
    parser.add_argument("--company", action="append", default=[], help="repeatable: a company_id")
    parser.add_argument("--seed-track", action="store_true", help="add the real 15 SEED companies")
    parser.add_argument(
        "--universe-track", action="store_true", help="add the real UNIVERSE-track selection"
    )
    parser.add_argument("--as-of", action="append", required=True, help="repeatable: YYYY-MM-DD")
    parser.add_argument("--requested-by", default="cli")
    args = parser.parse_args()

    as_of_dates = [dt.date.fromisoformat(s) for s in args.as_of]

    settings = load_settings()
    session_factory = make_session_factory(settings)

    with session_factory() as session:
        company_ids = [uuid.UUID(c) for c in args.company]
        if args.seed_track:
            company_ids.extend(seed_track_company_ids(session))
        if args.universe_track:
            company_ids.extend(universe_track_company_ids(session))
        if not company_ids:
            print("no companies given -- pass --company, --seed-track, and/or --universe-track")
            return 1

        exit_code = 0
        for company_id in company_ids:
            for as_of in as_of_dates:
                outcome = run_investigation(session, company_id, as_of, args.requested_by)
                print(
                    f"company={company_id} as_of={as_of} "
                    f"investigation_id={outcome.investigation.id} "
                    f"final_status={outcome.investigation.final_status} "
                    f"failure_reason={outcome.investigation.failure_reason}"
                )
                if outcome.investigation.final_status not in ("FINALISED", "NEEDS_REVIEW"):
                    exit_code = 1
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
