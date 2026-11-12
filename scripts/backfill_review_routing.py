"""Phase 6 Correction 2 §2.4: backfill real review tasks for every
currently-FINALISED/NEEDS_REVIEW investigation's own latest dossier,
under the fixed routing rules (`ledgerlight.agent.review.
determine_routing`'s now-corrected `high_severity_finding`,
`repair_removed_high_severity`, `repair_emptied_section`).

Idempotent and append-only: never creates a ReviewTask for a
(dossier_id, reason_code) pair that already has one open, so running
this twice -- or running it after the normal end-of-investigation
routing already created some of these tasks -- never duplicates a
real decision.

Usage:
    python3 -m uv run python scripts/backfill_review_routing.py [--apply]

Without --apply, prints what WOULD be created (a dry run).
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import select, text  # noqa: E402

from ledgerlight.agent.models import Claim, Dossier, Investigation, ReviewTask  # noqa: E402
from ledgerlight.agent.review import determine_routing  # noqa: E402
from ledgerlight.config.settings import load_settings  # noqa: E402
from ledgerlight.db.session import make_session_factory  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill real review-routing tasks.")
    parser.add_argument("--apply", action="store_true", help="commit new review_tasks rows")
    args = parser.parse_args()

    settings = load_settings()
    session_factory = make_session_factory(settings)

    counts: Counter[str] = Counter()
    created: list[tuple[str, str]] = []  # (dossier_id, reason_code)

    with session_factory() as session:
        rows = session.execute(
            text(
                """
                SELECT DISTINCT ON (investigation_id) id, investigation_id
                FROM dossiers
                ORDER BY investigation_id, version DESC
                """
            )
        ).all()
        print(f"latest dossier per real investigation: {len(rows)}")

        for dossier_id, investigation_id in rows:
            dossier = session.get(Dossier, dossier_id)
            investigation = session.get(Investigation, investigation_id)
            assert dossier is not None, f"dossier {dossier_id} vanished mid-sweep"
            assert investigation is not None, f"investigation {investigation_id} vanished mid-sweep"
            all_claims = session.scalars(
                select(Claim).where(Claim.investigation_id == investigation_id)
            ).all()
            active_claims = [c for c in all_claims if c.verification_status != "failed"]
            failed_claims = [c for c in all_claims if c.verification_status == "failed"]

            decisions = determine_routing(
                session, investigation, dossier, active_claims, failed_claims
            )
            existing_reasons = set(
                session.scalars(
                    select(ReviewTask.reason_code).where(ReviewTask.dossier_id == dossier_id)
                ).all()
            )
            for decision in decisions:
                counts[decision.reason_code] += 1
                if decision.reason_code in existing_reasons:
                    continue
                created.append((str(dossier_id), decision.reason_code))
                if args.apply:
                    session.add(
                        ReviewTask(
                            dossier_id=dossier_id,
                            reason_code=decision.reason_code,
                            priority=decision.priority,
                            status="open",
                        )
                    )
                    existing_reasons.add(decision.reason_code)  # avoid a 2nd dup within this run

        if args.apply and created:
            session.commit()

    print("\n--- real counts by reason code (every rule that fires, including pre-existing) ---")
    for reason, count in counts.most_common():
        print(f"  {reason}: {count}")

    action = "created" if args.apply else "WOULD be created (dry run, pass --apply to commit)"
    print(f"\n--- {len(created)} new review_tasks {action} ---")
    for dossier_id, reason_code in created:
        print(f"  dossier={dossier_id} reason={reason_code}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
