"""Phase 4 §5/§14.9: runs the real NLI entailment threshold calibration
against the SYNTHETIC labelled set
(`ledgerlight.agent.nli_calibration.SYNTHETIC_ENTAILMENT_EXAMPLES`) and
writes the real result to `docs/agent/nli-calibration.json`, for
citation in the final report."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from ledgerlight.agent.nli_calibration import (  # noqa: E402
    calibrate_threshold,
    print_calibration_report,
)

OUTPUT_PATH = REPO_ROOT / "docs" / "agent" / "nli-calibration.json"


def main() -> int:
    result = calibrate_threshold()
    print_calibration_report(result)

    assert result.best is not None
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(
            {
                "note": "SYNTHETIC labelled set -- not real gold labels",
                "best_threshold": result.best.threshold,
                "best_precision": result.best.precision,
                "best_recall": result.best.recall,
                "best_f1": result.best.f1,
                "candidates": [
                    {
                        "threshold": c.threshold,
                        "precision": c.precision,
                        "recall": c.recall,
                        "f1": c.f1,
                        "tp": c.true_positives,
                        "fp": c.false_positives,
                        "tn": c.true_negatives,
                        "fn": c.false_negatives,
                    }
                    for c in result.candidates
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nwrote {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
