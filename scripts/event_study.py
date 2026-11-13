"""Enhancement 1 §2 `event-study` command: runs the real, pre-
registered governance event study (`ledgerlight.research.event_study`)
against the live DB, under a real, already-frozen spec (the spec-hash
freeze guard refuses to run under a spec edited after it was frozen --
see `scripts/event_study_register_spec.py`), and prints the real raw
output the brief asks for: the spec hash, event counts per filter
stage, the CAR tables, and the placebo comparison.

Usage:
    python3 -m uv run python scripts/event_study.py run \
        --spec docs/enhancements/event-study/spec.v1.json --version v1
    python3 -m uv run python scripts/event_study.py report
"""

from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import select  # noqa: E402

from ledgerlight.config.settings import load_settings  # noqa: E402
from ledgerlight.db.session import make_session_factory  # noqa: E402
from ledgerlight.research.event_study import (  # noqa: E402
    current_git_sha,
    load_and_verify_spec,
    run_event_study,
)
from ledgerlight.research.models import EventStudyRun  # noqa: E402
from ledgerlight.research.report import generate_report  # noqa: E402


def _print_run_result(stage_counts: dict[str, object], metrics: dict[str, object]) -> None:
    print("\n--- real event counts per filter stage ---")
    for stage, count in stage_counts.items():
        print(f"  {stage}: {count}")

    print("\n--- real CAR tables (per event type, window) ---")
    for event_type, windows in metrics.items():
        if event_type == "_robustness":
            continue
        print(f"\n  {event_type}:")
        for window_name, m in windows.items():  # type: ignore[attr-defined]
            print(
                f"    {window_name}: n={m['n']} mean_car={m['mean_car']} "
                f"median_car={m['median_car']} "
                f"t={m['t_stat']} t_p={m['t_p']} t_p_holm={m['t_p_holm']} "
                f"bmp={m['bmp_stat']} bmp_p={m['bmp_p']} bmp_p_holm={m['bmp_p_holm']} "
                f"rank={m['rank_stat']} rank_p={m['rank_p']} rank_p_holm={m['rank_p_holm']}"
            )

    robustness = metrics.get("_robustness", {})
    print("\n--- real robustness checks (primary window only) ---")
    for event_type, r in robustness.items():  # type: ignore[attr-defined]
        print(f"  {event_type}: {r}")


def main() -> int:
    parser = argparse.ArgumentParser(description="The real governance event study CLI.")
    sub = parser.add_subparsers(dest="command", required=True)

    run_parser = sub.add_parser("run", help="run the real, pre-registered event study")
    run_parser.add_argument("--spec", required=True, help="path to the machine-readable spec JSON")
    run_parser.add_argument("--version", required=True, help='spec version, e.g. "v1"')
    run_parser.add_argument("--requested-by", default="event-study-cli")

    sub.add_parser("report", help="print and write the latest real run's report")

    args = parser.parse_args()
    settings = load_settings()
    session_factory = make_session_factory(settings)

    if args.command == "run":
        spec_path = Path(args.spec)
        with session_factory() as session:
            spec = load_and_verify_spec(session, spec_path, args.version)
            print(f"spec {spec.version} verified, real sha256={spec.sha256}")
            git_sha = current_git_sha(REPO_ROOT)
            result = run_event_study(session, spec, git_sha, args.requested_by)
        print(f"\nrun_id={result.run_id}")
        _print_run_result(dict(result.event_counts_json), dict(result.metrics_json))
        return 0

    if args.command == "report":
        with session_factory() as session:
            latest_id = session.execute(
                select(EventStudyRun.id).order_by(EventStudyRun.created_at.desc()).limit(1)
            ).scalar_one_or_none()
            if latest_id is None:
                print("no real event_study_runs row exists yet -- run `event-study run` first.")
                return 1
            run_id = uuid.UUID(str(latest_id))
            report_path = generate_report(session, run_id, REPO_ROOT)
        print(f"real report written to {report_path}")
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
