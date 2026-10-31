"""Phase 3 §9 `ablation` command: runs the real Sec7 ablation arms --
(a) STRUCTURED, (b) +RULE-VERIFIED, (c) +EVENT-CANDIDATE (unverified)
-- against the verified-coverage dataset and prints the real deltas."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from ledgerlight.config.settings import load_settings  # noqa: E402
from ledgerlight.db.session import make_session_factory  # noqa: E402
from ledgerlight.modelling.ablation import print_ablation_result, run_ablation  # noqa: E402
from ledgerlight.modelling.coverage import compute_verified_coverage  # noqa: E402
from ledgerlight.modelling.dataset import build_primary_outcome_dataset  # noqa: E402


def main() -> int:
    settings = load_settings()
    session_factory = make_session_factory(settings)

    with session_factory() as session:
        coverage = compute_verified_coverage(session)
        rows = build_primary_outcome_dataset(session, coverage)
        result = run_ablation(rows, session)

    print_ablation_result(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
