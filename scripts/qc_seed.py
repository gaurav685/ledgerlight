"""Phase 4 §10 `qc-seed` command: injects real, deliberately flawed
dossiers into the real review queue (`ledgerlight.agent.qc_seed`) and
reports the real reviewer catch rate per flaw type."""

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
from ledgerlight.agent.qc_seed import (  # noqa: E402
    ALL_FLAW_TYPES,
    compute_catch_rate_report,
    print_catch_rate_report,
    seed_flawed_dossier,
    seed_qc_batch,
)
from ledgerlight.config.settings import load_settings  # noqa: E402
from ledgerlight.db.session import make_session_factory  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed real QC items / report catch rate.")
    sub = parser.add_subparsers(dest="command", required=True)

    seed_parser = sub.add_parser("seed", help="seed one real flawed dossier")
    seed_parser.add_argument("--company", required=True)
    seed_parser.add_argument("--as-of", required=True, help="YYYY-MM-DD")
    seed_parser.add_argument("--flaw-type", required=True, choices=list(ALL_FLAW_TYPES))
    seed_parser.add_argument("--requested-by", default="qc-seed")

    batch_parser = sub.add_parser("batch", help="seed a real, deterministic share of a batch")
    batch_parser.add_argument("--company", action="append", default=[])
    batch_parser.add_argument("--seed-track", action="store_true")
    batch_parser.add_argument("--universe-track", action="store_true")
    batch_parser.add_argument("--as-of", required=True, help="YYYY-MM-DD applied to every target")
    batch_parser.add_argument("--fraction", type=float, required=True)
    batch_parser.add_argument("--rng-seed", type=int, default=0)
    batch_parser.add_argument("--requested-by", default="qc-seed")

    sub.add_parser("catch-rate", help="report the real reviewer catch rate per flaw type")

    args = parser.parse_args()

    settings = load_settings()
    session_factory = make_session_factory(settings)

    with session_factory() as session:
        if args.command == "seed":
            item = seed_flawed_dossier(
                session,
                uuid.UUID(args.company),
                dt.date.fromisoformat(args.as_of),
                args.flaw_type,
                requested_by=args.requested_by,
            )
            print(
                f"seeded: investigation={item.investigation_id} dossier={item.dossier_id} "
                f"review_task={item.review_task_id} flaw_type={item.flaw_type}"
            )
            return 0

        if args.command == "batch":
            as_of = dt.date.fromisoformat(args.as_of)
            targets = [(uuid.UUID(c), as_of) for c in args.company]
            if args.seed_track:
                targets.extend((cid, as_of) for cid in seed_track_company_ids(session))
            if args.universe_track:
                targets.extend((cid, as_of) for cid in universe_track_company_ids(session))
            if not targets:
                print("no targets given -- pass --company, --seed-track, and/or --universe-track")
                return 1

            def _on_skip(
                company_id: uuid.UUID, as_of: dt.date, flaw_type: str, reason: str
            ) -> None:
                print(
                    f"  skipped company={company_id} as_of={as_of} flaw_type={flaw_type}: {reason}"
                )

            items = seed_qc_batch(
                session,
                targets,
                args.fraction,
                requested_by=args.requested_by,
                rng_seed=args.rng_seed,
                on_skip=_on_skip,
            )
            print(f"seeded {len(items)} real flawed dossier(s) of {len(targets)} real target(s)")
            for item in items:
                print(f"  company={item.company_id} flaw_type={item.flaw_type}")
            return 0

        if args.command == "catch-rate":
            report = compute_catch_rate_report(session)
            print_catch_rate_report(report)
            return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
