"""One-time migration: fix the real company-fragmentation bug (one
Company row per ISIN instead of per real company) left behind by the
original bootstrap_companies.py -- see ledgerlight.ingestion
.company_grouping's docstring and docs/phase-3/phase-3-report.md's
Sec2.4 addendum for the full writeup.

Core grouping/merge logic now lives in `ledgerlight.ingestion
.company_dedup`, shared with `scripts/bootstrap_companies.py`, which
calls it on every run so this class of bug self-heals instead of
requiring a manual re-run of this script every time (see that module's
docstring for the real recurrence found 2026-10-31).

Safety:
- Default is --dry-run: prints exactly what would change, touches
  nothing. Pass --apply to actually commit.
- A Filing row's (version_id, company_id) is unique; if merging would
  create a duplicate pair, the redundant Filing row is deleted (not
  silently -- counted and reported) rather than violating the
  constraint.
- Writes a before-state evidence file (every affected row, by table)
  so the migration is auditable after the fact, not just trusted.

Usage:
    python scripts/migrate_company_dedup.py --dry-run
    python scripts/migrate_company_dedup.py --apply
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import cast

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from ledgerlight.config.settings import load_settings  # noqa: E402
from ledgerlight.db.session import make_session_factory  # noqa: E402
from ledgerlight.ingestion.company_dedup import (  # noqa: E402
    find_fragmented_groups,
    load_groups,
    merge_fragmented_groups,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    settings = load_settings()
    session_factory = make_session_factory(settings)

    with session_factory() as session:
        groups = load_groups(session)
        fragmented = find_fragmented_groups(session, groups)

        if args.dry_run:
            before_state = [
                {
                    "group_isins": group.isins,
                    "latest_symbol": group.latest_symbol,
                    "duplicate_company_count": len(existing_company_ids),
                }
                for group, existing_company_ids in fragmented
            ]
            evidence_path = (
                REPO_ROOT / "docs" / "phase-3" / "evidence" / "company-dedup-dry-run.json"
            )
            evidence_path.write_text(json.dumps(before_state, indent=2, default=str))
            print(f"[DRY RUN] fragmented_groups_found: {len(fragmented)}")
            print(
                f"[DRY RUN] would delete "
                f"{sum(len(ids) - 1 for _, ids in fragmented)} duplicate company rows"
            )
            print(f"[DRY RUN] full plan written to {evidence_path}")
            return 0

        stats = merge_fragmented_groups(session, fragmented)
        session.commit()

        evidence_path = (
            REPO_ROOT / "docs" / "phase-3" / "evidence" / "company-dedup-apply-run2-applied.json"
        )
        evidence_text = json.dumps(cast(object, stats.before_state), indent=2, default=str)
        evidence_path.write_text(evidence_text)

    print(f"fragmented_groups_fixed: {stats.fragmented_groups}")
    print(f"companies_deleted: {stats.companies_deleted}")
    print(f"identifiers_regenerated: {stats.identifiers_regenerated}")
    print(f"filings_repointed: {stats.filings_repointed}")
    print(f"filings_deleted_as_duplicate: {stats.filings_deleted_as_duplicate}")
    print(f"events_repointed: {stats.events_repointed}")
    print(f"label_items_repointed: {stats.label_items_repointed}")
    print(f"entities_repointed: {stats.entities_repointed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
