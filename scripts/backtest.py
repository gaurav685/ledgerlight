"""Phase 3 §9 `backtest` command: runs the real Sec6/7 walk-forward
backtest and prints the fold table, pooled metrics, and honest
distinct-event/company counts. Records the run as a real
`experiments` row and, if a previous run against the exact same real
data snapshot exists, prints the diff against it -- proving
`backtest` is reproducible per snapshot (§9's explicit requirement:
"Re-running backtest on the same snapshot gives identical metrics.
Show the diff.").
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import text  # noqa: E402

from ledgerlight.config.settings import load_settings  # noqa: E402
from ledgerlight.db.session import make_session_factory  # noqa: E402
from ledgerlight.modelling.backtest import MODEL_NAMES, run_backtest  # noqa: E402
from ledgerlight.modelling.coverage import compute_verified_coverage  # noqa: E402
from ledgerlight.modelling.dataset import DatasetRow, build_primary_outcome_dataset  # noqa: E402
from ledgerlight.modelling.folds import print_fold_table  # noqa: E402
from ledgerlight.modelling.reporting import print_positive_counts  # noqa: E402
from ledgerlight.modelling.scoring import record_experiment, write_experiment_doc  # noqa: E402

CONFIG: dict[str, object] = {"command": "backtest", "seed": 42}
SEED = 42
EXPERIMENTS_DOC_DIR = REPO_ROOT / "docs" / "experiments"


def _git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True
        ).strip()
    except Exception:
        return "unknown"


def _dataset_snapshot_hash(rows: list[DatasetRow]) -> str:
    pairs = sorted((str(r.company_id), str(r.as_of), r.label, r.censored) for r in rows)
    blob = "\n".join(f"{c}:{a}:{label}:{censored}" for c, a, label, censored in pairs).encode()
    return hashlib.sha256(blob).hexdigest()


def _metrics_summary(result: Any) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for name in MODEL_NAMES:
        metrics = result.pooled_outputs[name].metrics
        summary[name] = {
            "pr_auc": metrics.pr_auc,
            "roc_auc": metrics.roc_auc,
            "brier_skill_score": metrics.brier_skill_score,
            "n": metrics.n,
        }
    counts = result.pooled_positive_counts
    summary["positive_counts"] = {
        "company_month_rows": counts.company_month_rows,
        "distinct_positive_companies": counts.distinct_positive_companies,
        "distinct_positive_events": counts.distinct_positive_events,
        "is_inconclusive": counts.is_inconclusive,
    }
    return summary


def main() -> int:
    settings = load_settings()
    session_factory = make_session_factory(settings)

    with session_factory() as session:
        coverage = compute_verified_coverage(session)
        rows = build_primary_outcome_dataset(session, coverage)
        result = run_backtest(rows, coverage, seed=SEED)

        print(f"coverage window: {coverage.window_start} {coverage.window_end}")
        print(f"companies: {coverage.company_names}")
        print_fold_table(result.folds)
        print_positive_counts("pooled", [row for row in rows if not row.censored])

        metrics_summary = _metrics_summary(result)
        for name, metrics in metrics_summary.items():
            print(f"{name}: {metrics}")

        snapshot_hash = _dataset_snapshot_hash(rows)
        config = {**CONFIG, "data_snapshot_hash": snapshot_hash}

        previous = session.execute(
            text(
                "SELECT metrics_json FROM experiments "
                "WHERE data_snapshot_hashes->>'dataset' = :hash "
                "AND config_json->>'command' = 'backtest' "
                "ORDER BY created_at DESC LIMIT 1"
            ),
            {"hash": snapshot_hash},
        ).one_or_none()

        git_sha = _git_sha()
        experiment_id = record_experiment(
            session,
            config=config,
            data_snapshot_hashes={"dataset": snapshot_hash},
            git_sha=git_sha,
            metrics=metrics_summary,
        )
        session.commit()

        doc_path = write_experiment_doc(
            experiment_id,
            config=config,
            data_snapshot_hashes={"dataset": snapshot_hash},
            git_sha=git_sha,
            metrics=metrics_summary,
            output_dir=EXPERIMENTS_DOC_DIR,
        )
        print(f"wrote {doc_path}")

    if previous is None:
        print(
            "no previous backtest run recorded against this exact data snapshot -- nothing to diff"
        )
    else:
        previous_metrics = previous[0]
        if previous_metrics == metrics_summary:
            print(
                "backtest reproducibility: IDENTICAL to the previous run on this snapshot (0 diffs)"
            )
        else:
            print("backtest reproducibility: DIFFERS from the previous run on this snapshot:")
            for key, value in metrics_summary.items():
                if previous_metrics.get(key) != value:
                    print(f"  {key}: before={previous_metrics.get(key)} after={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
