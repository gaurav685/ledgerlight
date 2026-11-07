"""Phase 6A §7: shared infrastructure for the human review pack's four
file-backed review types (field, entity-pair, retrieval,
outcome-evidence). Dossier review is not here -- it already has a real,
DB-backed flow (`ledgerlight.agent.review`, `scripts/dossier_review.py`).

Phase 6 Correction 1 (2026-11-07): an AI session was run against these
tools under an explicit user override, producing real QA findings but
never real human review -- see `docs/phase-6/phase-6b-review-findings.md`
and `docs/phase-6/phase-6-correction-1.md`. `require_human_confirmation`
below is the real, tested guard added so that can never happen silently
again: every CLI in this package now refuses to record a decision
unless `--human` is passed explicitly, and a human typing that flag for
an AI session would be lying about who is reviewing, not a gap the tool
quietly allows.
"""

from __future__ import annotations

import argparse
import sys


def require_human_confirmation(args: argparse.Namespace) -> None:
    """Refuses to proceed unless `args.human` is True. Call this right
    after `parse_args()`, before any decision-recording code runs, in
    every CLI that records a real reviewer decision (field/entity-pair/
    retrieval/outcome-evidence review, and dossier `decide`/`feedback`).
    `--reviewer` is already `required=True` on every one of these
    parsers; this adds the second, independent confirmation the brief
    asked for."""
    if not getattr(args, "human", False):
        print(
            "Refusing to record a decision: --human was not passed. "
            "This tool is for a real human reviewer only -- if you are "
            "a human, re-run with --human. An AI session must not pass "
            "this flag (doing so would misrepresent who is reviewing); "
            "see docs/phase-6/phase-6-correction-1.md.",
            file=sys.stderr,
        )
        raise SystemExit(2)
