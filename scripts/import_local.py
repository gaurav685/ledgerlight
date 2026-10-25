"""Entrypoint: import manually-downloaded documents from data/inbox/.

See docs/data/manual-download-checklist.md for what belongs in the inbox
and why (documents only reachable via BSE/NSE, which our acquisition tool
is blocked from — see docs/data/source-inventory.md).
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from ledgerlight.acquisition.import_local import import_inbox  # noqa: E402
from ledgerlight.config.settings import load_settings  # noqa: E402


def main() -> int:
    settings = load_settings()
    result = import_inbox(data_dir=settings.data_dir)

    print(f"Imported: {len(result.imported)}")
    for name in result.imported:
        print(f"  + {name}")
    print(f"Skipped (duplicate content): {len(result.skipped_duplicate)}")
    for name in result.skipped_duplicate:
        print(f"  = {name}")
    print(f"Rejected (no provenance.csv row): {len(result.rejected_no_provenance)}")
    for name in result.rejected_no_provenance:
        print(f"  ! {name}")

    return 1 if result.rejected_no_provenance else 0


if __name__ == "__main__":
    raise SystemExit(main())
