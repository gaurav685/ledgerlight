"""Phase 3 Sec2.4: report, per discovery source (care/ibbi/sebi), how many
fetched documents auto-link to a real Company via company_identifiers,
versus unmatched. "Auto-linked" means an exact identifier match
(NSE_SYMBOL, BSE_CODE or ISIN) against company_identifiers -- no fuzzy
matching, so there is no "review-queued" tier here: a document either
resolves exactly or it doesn't. Per the brief: only auto-linked results
are usable downstream; unmatched ones are reported, not guessed at.

Usage: python scripts/entity_link_report.py
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import select  # noqa: E402

from ledgerlight.config.settings import load_settings  # noqa: E402
from ledgerlight.db.models import Document  # noqa: E402
from ledgerlight.db.session import make_session_factory  # noqa: E402
from ledgerlight.knowledge.models import CompanyIdentifier  # noqa: E402

DISCOVERY_SOURCES = ("care", "ibbi", "sebi")


def main() -> int:
    settings = load_settings()
    session_factory = make_session_factory(settings)

    with session_factory() as session:
        # Build lookup sets once, not one query per document.
        by_type: dict[str, set[str]] = {"NSE_SYMBOL": set(), "BSE_CODE": set(), "ISIN": set()}
        for identifier_type, value in session.execute(
            select(CompanyIdentifier.identifier_type, CompanyIdentifier.value)
        ).all():
            if identifier_type in by_type:
                by_type[identifier_type].add(value)

        for source_id in DISCOVERY_SOURCES:
            docs = (
                session.execute(select(Document).where(Document.source_id == source_id))
                .scalars()
                .all()
            )
            auto_linked = 0
            unmatched: list[tuple[str | None, str | None, str | None]] = []
            unmatched_field_counter: Counter[str] = Counter()
            for doc in docs:
                matched = (
                    (doc.nse_symbol and doc.nse_symbol in by_type["NSE_SYMBOL"])
                    or (doc.bse_code and doc.bse_code in by_type["BSE_CODE"])
                    or (doc.isin and doc.isin in by_type["ISIN"])
                )
                if matched:
                    auto_linked += 1
                else:
                    unmatched.append((doc.nse_symbol, doc.bse_code, doc.isin))
                    only_field = (
                        "bse_code_only"
                        if (doc.bse_code and not doc.nse_symbol and not doc.isin)
                        else "other"
                    )
                    unmatched_field_counter[only_field] += 1

            print(
                f"{source_id}: total={len(docs)} auto_linked={auto_linked} "
                f"unmatched={len(unmatched)}"
            )
            if unmatched_field_counter:
                print(f"  unmatched breakdown: {dict(unmatched_field_counter)}")
            distinct_unmatched_bse = sorted({u[1] for u in unmatched if u[1]})
            if distinct_unmatched_bse:
                print(f"  distinct unmatched BSE codes: {distinct_unmatched_bse}")

        print()
        print("company_identifiers totals:")
        for t in ("NSE_SYMBOL", "BSE_CODE", "ISIN"):
            print(f"  {t}: {len(by_type[t])} distinct values")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
