"""Bootstraps real company and audit_firm entities from Phase 2's own
output (filings, event_fields), then resolves/links them. Idempotent."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from ledgerlight.config.settings import load_settings  # noqa: E402
from ledgerlight.db.session import make_session_factory  # noqa: E402
from ledgerlight.knowledge.entity_bootstrap import (  # noqa: E402
    bootstrap_audit_firm_entities,
    bootstrap_company_entities,
)


def main() -> int:
    settings = load_settings()
    session_factory = make_session_factory(settings)

    with session_factory() as session:
        company_stats = bootstrap_company_entities(session)
        audit_stats = bootstrap_audit_firm_entities(session)

    print(f"company_entities_created: {company_stats.company_entities_created}")
    print(f"company_entities_already_present: {company_stats.company_entities_already_present}")
    print(f"audit_firm_mentions_created: {audit_stats.audit_firm_mentions_created}")
    print(f"audit_firm_entities_created: {audit_stats.audit_firm_entities_created}")
    print(f"audit_firm_links_created: {audit_stats.audit_firm_links_created}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
