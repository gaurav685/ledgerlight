"""Run one source's Dagster ingestion job, in-process, against the real
DagsterInstance (DAGSTER_HOME must point at dagster_home/ — see
docs/ingestion/runbook.md). This is the single-source equivalent of the
daily schedule / inbox sensor firing a run.

Usage:
    python scripts/ingest.py SOURCE_ID [PARTITION_DATE]

SOURCE_ID is any of the known_items sources (sebi, ibbi, care, *_ir) or
"nse_archives" (requires PARTITION_DATE, YYYY-MM-DD) or "inbox".
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from dagster import DagsterInstance  # noqa: E402

from ledgerlight.orchestration.definitions import _KNOWN_ITEM_SOURCES, defs  # noqa: E402


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: python scripts/ingest.py SOURCE_ID [PARTITION_DATE]")
        return 2
    source_id = sys.argv[1]
    instance = DagsterInstance.get()

    if source_id == "nse_archives":
        if len(sys.argv) != 3:
            print("nse_archives requires a PARTITION_DATE (YYYY-MM-DD)")
            return 2
        job_def = defs.get_job_def("bhavcopy_job")
        result = job_def.execute_in_process(instance=instance, partition_key=sys.argv[2])
    elif source_id == "inbox":
        job_def = defs.get_job_def("inbox_import_job")
        result = job_def.execute_in_process(instance=instance)
    elif source_id in _KNOWN_ITEM_SOURCES:
        job_def = defs.get_job_def(f"{source_id}_job")
        result = job_def.execute_in_process(instance=instance)
    else:
        print(f"unknown source_id: {source_id!r}")
        return 2

    print(f"run_id: {result.run_id}")
    print(f"success: {result.success}")
    return 0 if result.success else 1


if __name__ == "__main__":
    raise SystemExit(main())
