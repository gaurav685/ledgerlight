"""Phase 3 §9 `leakage-check` command: runs every real §7 leakage
check against the verified-coverage dataset and prints the report.
Exits non-zero if the outcome-date or embargo checks find a real
violation (the label-permutation, feature-shift and univariate flags
are reported for human judgment, not treated as hard failures, since
a noisy tiny-sample result can legitimately look anomalous without
being a bug)."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from ledgerlight.config.settings import load_settings  # noqa: E402
from ledgerlight.db.session import make_session_factory  # noqa: E402
from ledgerlight.modelling.backtest import run_backtest  # noqa: E402
from ledgerlight.modelling.coverage import compute_verified_coverage  # noqa: E402
from ledgerlight.modelling.dataset import build_primary_outcome_dataset  # noqa: E402
from ledgerlight.modelling.leakage import print_leakage_report, run_leakage_report  # noqa: E402
from ledgerlight.modelling.models import ALL_STRUCTURED_AND_RULE_VERIFIED_FEATURES  # noqa: E402


def main() -> int:
    settings = load_settings()
    session_factory = make_session_factory(settings)

    with session_factory() as session:
        coverage = compute_verified_coverage(session)
        rows = build_primary_outcome_dataset(session, coverage)
        real_backtest = run_backtest(rows, coverage)
        report = run_leakage_report(
            rows, coverage, ALL_STRUCTURED_AND_RULE_VERIFIED_FEATURES, real_backtest
        )

    print_leakage_report(report)
    if not report.passed:
        print("LEAKAGE CHECK FAILED: real outcome-date or embargo violations found")
        return 1
    print("LEAKAGE CHECK PASSED: 0 outcome-date violations, 0 embargo violations")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
