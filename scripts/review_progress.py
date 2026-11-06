"""Phase 6A §7 `review-progress` command: shows real counts per review
type and per reviewer, across all 5 human review pack types (field,
entity-pair, retrieval, outcome-evidence, dossier).

Usage:
    python3 -m uv run python scripts/review_progress.py
"""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import select  # noqa: E402

from ledgerlight.agent.models import ReviewDecisionAudit  # noqa: E402
from ledgerlight.config.settings import load_settings  # noqa: E402
from ledgerlight.db.session import make_session_factory  # noqa: E402
from ledgerlight.review_pack.audit import counts_by_reviewer, progress_counts  # noqa: E402

REVIEW_PACK_DIR = REPO_ROOT / "docs" / "phase-6" / "review-pack"
FILE_BACKED_TYPES: dict[str, Path] = {
    "field review": REVIEW_PACK_DIR / "field-review-audit.jsonl",
    "entity-pair review": REVIEW_PACK_DIR / "entity-pair-review-audit.jsonl",
    "retrieval review": REVIEW_PACK_DIR / "retrieval-review-audit.jsonl",
    "outcome-evidence review": REVIEW_PACK_DIR / "outcome-evidence-review-audit.jsonl",
}
DOSSIER_MANIFEST_PATH = REVIEW_PACK_DIR / "dossier-review-manifest.jsonl"


def _print_section(name: str, by_decision: dict[str, int], by_reviewer: dict[str, int]) -> None:
    total = sum(by_decision.values())
    print(f"\n{name}: {total} decided")
    if by_decision:
        for decision, count in sorted(by_decision.items()):
            print(f"  {decision}: {count}")
    if by_reviewer:
        print("  by reviewer:")
        for reviewer, count in sorted(by_reviewer.items()):
            print(f"    {reviewer}: {count}")


def _manifest_task_ids() -> set[str]:
    if not DOSSIER_MANIFEST_PATH.exists():
        return set()
    with DOSSIER_MANIFEST_PATH.open(encoding="utf-8") as fh:
        return {json.loads(line)["review_task_id"] for line in fh if line.strip()}


def main() -> int:
    for name, audit_path in FILE_BACKED_TYPES.items():
        _print_section(name, progress_counts(audit_path), counts_by_reviewer(audit_path))

    # Dossier review: DB-backed, scoped to this phase's own §7 sample
    # (the manifest's own review_task_ids), via the real append-only
    # review_decisions_audit.
    sample_task_ids = _manifest_task_ids()
    if not sample_task_ids:
        print(
            "\ndossier review: 0 decided (no "
            "docs/phase-6/review-pack/dossier-review-manifest.jsonl yet -- run "
            "scripts/build_dossier_review_sample.py first)"
        )
        return 0

    settings = load_settings()
    session_factory = make_session_factory(settings)
    with session_factory() as session:
        audits = session.scalars(
            select(ReviewDecisionAudit)
            .where(ReviewDecisionAudit.action == "decided")
            .where(ReviewDecisionAudit.review_task_id.in_({uuid.UUID(t) for t in sample_task_ids}))
        ).all()
        by_decision: dict[str, int] = {}
        by_reviewer: dict[str, int] = {}
        for audit in audits:
            after = audit.after or {}
            decision = str(after.get("decision", "unknown"))
            by_decision[decision] = by_decision.get(decision, 0) + 1
            by_reviewer[audit.actor] = by_reviewer.get(audit.actor, 0) + 1
        _print_section(
            f"dossier review ({len(sample_task_ids)}-item §7 sample)", by_decision, by_reviewer
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
