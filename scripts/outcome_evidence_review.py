"""Phase 6A §7 `outcome-evidence-review` command: a real human review
CLI over every real positive primary-outcome event (if 60 or fewer --
otherwise a stratified sample of 60, by outcome type and year).
Records two real reviewer decisions per item: whether the evidence
supports the outcome (yes / no / unclear), and whether the date is
correct (yes / no) -- to an append-only audit log.

Usage:
    python3 -m uv run python scripts/outcome_evidence_review.py --reviewer "your name"

Resumes automatically (see field_review.py's own docstring for the
mechanism -- identical here).
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from ledgerlight.config.settings import load_settings  # noqa: E402
from ledgerlight.db.session import make_session_factory  # noqa: E402
from ledgerlight.knowledge.models import Company, Event, Outcome  # noqa: E402
from ledgerlight.review_pack.audit import append_entry, latest_decisions  # noqa: E402

AUDIT_PATH = REPO_ROOT / "docs" / "phase-6" / "review-pack" / "outcome-evidence-review-audit.jsonl"
PRIMARY_OUTCOME_TYPES = ("PRIMARY_IBBI_ADMISSION", "PRIMARY_RATING_DOWNGRADE_D")
MAX_SAMPLE = 60


def _stratum(outcome_type: str, year: int | None) -> str:
    bucket = "ibbi" if outcome_type == "PRIMARY_IBBI_ADMISSION" else "rating_default"
    return f"{bucket}:{year}"


def _select_outcomes(session: Session) -> tuple[list[Outcome], bool]:
    all_outcomes = list(
        session.scalars(
            select(Outcome)
            .where(Outcome.outcome_type.in_(PRIMARY_OUTCOME_TYPES))
            .order_by(Outcome.id)
        ).all()
    )
    if len(all_outcomes) <= MAX_SAMPLE:
        return all_outcomes, False

    # Stratified: proportional, deterministic round-robin per (type, year)
    # stratum, ordered by id within each stratum.
    by_stratum: dict[str, list[Outcome]] = defaultdict(list)
    for o in all_outcomes:
        year = o.observed_at.year if o.observed_at else None
        by_stratum[_stratum(o.outcome_type or "", year)].append(o)
    for bucket in by_stratum.values():
        bucket.sort(key=lambda o: str(o.id))

    selected: list[Outcome] = []
    strata_keys = sorted(by_stratum)
    idx = 0
    while len(selected) < MAX_SAMPLE and any(by_stratum[k] for k in strata_keys):
        key = strata_keys[idx % len(strata_keys)]
        if by_stratum[key]:
            selected.append(by_stratum[key].pop(0))
        idx += 1
    selected.sort(key=lambda o: str(o.id))
    return selected, True


def main() -> int:
    parser = argparse.ArgumentParser(description="Real human outcome-evidence review CLI.")
    parser.add_argument("--reviewer", required=True, help="your name/identifier")
    parser.add_argument("--limit", type=int, default=None, help="cap items shown this run")
    args = parser.parse_args()

    settings = load_settings()
    session_factory = make_session_factory(settings)

    decided = latest_decisions(AUDIT_PATH)
    print(f"{len(decided)} item(s) already decided (resuming).")

    reviewed_this_run = 0
    with session_factory() as session:
        outcomes, was_stratified = _select_outcomes(session)
        print(
            f"{len(outcomes)} real primary-outcome events selected"
            + (" (stratified sample of 60 by type/year)" if was_stratified else " (all of them)")
        )
        pending = [o for o in outcomes if str(o.id) not in decided]
        if args.limit is not None:
            pending = pending[: args.limit]
        print(f"{len(pending)} pending item(s) of {len(outcomes)}.")

        for outcome in pending:
            event = session.get(Event, outcome.event_id)
            company = session.get(Company, event.company_id) if event and event.company_id else None
            print("\n" + "=" * 70)
            print(f"outcome_id: {outcome.id}")
            print(f"outcome_type: {outcome.outcome_type}")
            print(f"company: {company.display_name if company else '?'}")
            print(f"observed_at: {outcome.observed_at}")
            print(f"evidence (outcome_value): {outcome.outcome_value}")

            supports = (
                input(
                    "evidence supports the outcome? [y]es / [n]o / [u]nclear / [k]skip / [q]uit > "
                )
                .strip()
                .lower()
            )
            if supports == "q":
                break
            support_map = {"y": "yes", "n": "no", "u": "unclear", "k": "skip"}
            support_decision = support_map.get(supports)
            if support_decision is None:
                print("unrecognised choice, skipping this item")
                continue

            note = None
            date_decision = None
            if support_decision == "skip":
                note = input("skip note (optional) > ").strip() or None
            else:
                date_ok = input("date is correct? [y]es / [n]o > ").strip().lower()
                date_decision = {"y": "yes", "n": "no"}.get(date_ok, "unclear")

            append_entry(
                AUDIT_PATH,
                item_id=str(outcome.id),
                decision=support_decision,
                reviewer=args.reviewer,
                note=note,
                extra={
                    "outcome_type": outcome.outcome_type,
                    "observed_at": outcome.observed_at.isoformat() if outcome.observed_at else None,
                    "date_correct": date_decision,
                    "was_stratified_sample": was_stratified,
                },
            )
            reviewed_this_run += 1

    print(f"\nreviewed this run: {reviewed_this_run}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
