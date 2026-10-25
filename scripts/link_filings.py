"""Link document_versions to companies (filings), via scripts/bootstrap_companies.py's
company_identifiers. Idempotent."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from ledgerlight.config.settings import load_settings  # noqa: E402
from ledgerlight.db.session import make_session_factory  # noqa: E402
from ledgerlight.knowledge.filings import link_filings  # noqa: E402


def main() -> int:
    settings = load_settings()
    session_factory = make_session_factory(settings)
    with session_factory() as session:
        stats = link_filings(session)

    print(f"filings_created: {stats.filings_created}")
    print(f"filings_already_present: {stats.filings_already_present}")
    print(f"bse_codes_backfilled: {stats.bse_codes_backfilled}")
    print(f"unresolved: {len(stats.unresolved)}")
    for u in stats.unresolved:
        print(f"  {u}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
