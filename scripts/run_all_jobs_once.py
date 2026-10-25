"""Execute every Dagster job defined in ledgerlight.orchestration.definitions
at least once, in-process, against the real Postgres-backed DagsterInstance
(DAGSTER_HOME must be set). Prints one line per job with its run_id and
success/failure, for pasting into the Phase 1 report. This is a one-time
manual proof-of-execution tool, not part of the ongoing orchestration.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from dagster import DagsterInstance  # noqa: E402

from ledgerlight.orchestration.definitions import (  # noqa: E402
    _KNOWN_ITEM_SOURCES,
    defs,
)


def main() -> int:
    instance = DagsterInstance.get()
    results: list[tuple[str, str, bool]] = []

    # bhavcopy_job is partitioned by day; run one real partition.
    bhavcopy_job = defs.get_job_def("bhavcopy_job")
    result = bhavcopy_job.execute_in_process(instance=instance, partition_key="2025-09-01")
    results.append(("bhavcopy_job", result.run_id, result.success))

    inbox_import_job = defs.get_job_def("inbox_import_job")
    result = inbox_import_job.execute_in_process(instance=instance)
    results.append(("inbox_import_job", result.run_id, result.success))

    for source_id in _KNOWN_ITEM_SOURCES:
        job_def = defs.get_job_def(f"{source_id}_job")
        result = job_def.execute_in_process(instance=instance)
        results.append((f"{source_id}_job", result.run_id, result.success))

    print("job_name,run_id,success")
    for name, run_id, success in results:
        print(f"{name},{run_id},{success}")

    failures = [r for r in results if not r[2]]
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
