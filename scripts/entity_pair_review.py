"""Phase 6A §7 `entity-pair-review` command: a real human review CLI
over real (mention, candidate entity) pairs, including near-threshold
matches, scored with the exact same real fuzzy-matching function
`ledgerlight.knowledge.entity_resolution` uses in production. Records
a real reviewer decision (same / different / unsure) to an append-only
audit log.

Usage:
    python3 -m uv run python scripts/entity_pair_review.py --reviewer "your name"

Resumes automatically (see field_review.py's own docstring for the
mechanism -- identical here).

**Honest disclosure, not a bug**: the brief's own target is ~20 pairs.
The real corpus currently supports only as many real (mention,
candidate entity) pairs as exist -- every real mention compared
against every real entity of the same type. As of this writing that is
5 mentions x up to a handful of real same-type entities. This mirrors
Phase 2's own disclosed finding ("the real corpus's entity surface is
too thin... to build a meaningful pair set without inventing cases",
docs/phase-2/phase-2-report.md §7e) -- this tool does not invent pairs
to reach 20; it reports exactly how many real ones exist and reviews
those.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from ledgerlight.config.settings import load_settings  # noqa: E402
from ledgerlight.db.session import make_session_factory  # noqa: E402
from ledgerlight.knowledge.entity_resolution import (  # noqa: E402
    AUTO_LINK_THRESHOLD,
    REVIEW_THRESHOLD,
    _fuzzy_score,
)
from ledgerlight.knowledge.models import Entity, EntityLink, Mention  # noqa: E402
from ledgerlight.review_pack import require_human_confirmation  # noqa: E402
from ledgerlight.review_pack.audit import append_entry, latest_decisions  # noqa: E402

AUDIT_PATH = REPO_ROOT / "docs" / "phase-6" / "review-pack" / "entity-pair-review-audit.jsonl"
TARGET_SAMPLE_SIZE = 20
TOP_N_CANDIDATES_PER_MENTION = 5


@dataclass(frozen=True)
class CandidatePair:
    pair_id: str
    mention_id: str
    mention_text: str
    entity_id: str
    entity_name: str
    score: float
    near_threshold: bool
    system_decision: str


def _real_pairs(session: Session) -> list[CandidatePair]:
    mentions = session.scalars(select(Mention).order_by(Mention.id)).all()
    entities_by_type: dict[str, list[Entity]] = {}
    for entity in session.scalars(select(Entity).order_by(Entity.id)).all():
        entities_by_type.setdefault(entity.entity_type, []).append(entity)

    existing_links = {
        (link.mention_id, link.entity_id): link
        for link in session.scalars(select(EntityLink)).all()
    }

    pairs: list[CandidatePair] = []
    for mention in mentions:
        candidates = entities_by_type.get(mention.guessed_entity_type or "", [])
        scored = sorted(
            (
                (entity, _fuzzy_score(mention.surface_text, entity.display_name))
                for entity in candidates
            ),
            key=lambda t: (-t[1], str(t[0].id)),
        )
        for entity, score in scored[:TOP_N_CANDIDATES_PER_MENTION]:
            link = existing_links.get((mention.id, entity.id))
            pairs.append(
                CandidatePair(
                    pair_id=f"{mention.id}:{entity.id}",
                    mention_id=str(mention.id),
                    mention_text=mention.surface_text,
                    entity_id=str(entity.id),
                    entity_name=entity.display_name,
                    score=score,
                    near_threshold=REVIEW_THRESHOLD <= score < AUTO_LINK_THRESHOLD,
                    system_decision=(
                        "auto_link"
                        if link is not None
                        else ("reject" if score < REVIEW_THRESHOLD else "review")
                    ),
                )
            )
    # near-threshold first (the brief's own explicit ask), then by score descending
    pairs.sort(key=lambda p: (not p.near_threshold, -p.score, p.pair_id))
    return pairs


def main() -> int:
    parser = argparse.ArgumentParser(description="Real human entity-pair review CLI.")
    parser.add_argument("--reviewer", required=True, help="your name/identifier")
    parser.add_argument("--limit", type=int, default=None, help="cap items shown this run")
    parser.add_argument(
        "--human",
        action="store_true",
        help="confirms a real human is reviewing -- required to record any decision",
    )
    args = parser.parse_args()
    require_human_confirmation(args)

    settings = load_settings()
    session_factory = make_session_factory(settings)

    decided = latest_decisions(AUDIT_PATH)
    print(f"{len(decided)} item(s) already decided (resuming).")

    reviewed_this_run = 0
    with session_factory() as session:
        pairs = _real_pairs(session)[:TARGET_SAMPLE_SIZE]
        if len(pairs) < TARGET_SAMPLE_SIZE:
            print(
                f"NOTE: only {len(pairs)} real (mention, candidate entity) pairs exist in the "
                f"current corpus -- target is ~{TARGET_SAMPLE_SIZE}. Not padded with invented "
                "pairs; see this script's own docstring."
            )
        pending = [p for p in pairs if p.pair_id not in decided]
        if args.limit is not None:
            pending = pending[: args.limit]
        print(f"{len(pending)} pending item(s) of {len(pairs)} real pairs.")

        for pair in pending:
            print("\n" + "=" * 70)
            print(f"pair_id: {pair.pair_id}")
            print(f"mention: {pair.mention_text!r}")
            print(f"candidate entity: {pair.entity_name!r}")
            print(f"fuzzy score: {pair.score:.1f}  near_threshold: {pair.near_threshold}")
            print(f"system's own decision: {pair.system_decision}")

            choice = input("[s]ame / [d]ifferent / [u]nsure / [k]skip / [q]uit > ").strip().lower()
            if choice == "q":
                break
            decision_map = {"s": "same", "d": "different", "u": "unsure", "k": "skip"}
            decision = decision_map.get(choice)
            if decision is None:
                print("unrecognised choice, skipping this item")
                continue

            note = None
            if decision == "skip":
                note = input("skip note (optional) > ").strip() or None

            append_entry(
                AUDIT_PATH,
                item_id=pair.pair_id,
                decision=decision,
                reviewer=args.reviewer,
                note=note,
                extra={
                    "mention_text": pair.mention_text,
                    "entity_name": pair.entity_name,
                    "score": pair.score,
                    "near_threshold": pair.near_threshold,
                    "system_decision": pair.system_decision,
                },
            )
            reviewed_this_run += 1

    print(f"\nreviewed this run: {reviewed_this_run}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
