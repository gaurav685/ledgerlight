"""Bootstrap companies/company_identifiers from real bhavcopy data (ISIN +
NSE symbol history via price_bars).

A real company is grouped by `ledgerlight.ingestion.company_grouping`'s
union-find over (isin, symbol) co-occurrence, NOT by ISIN alone -- see
that module's docstring for the real bug this fixes (DHFL-like bond
issuers fragmenting into one "company" per ISIN). A symbol change over
time still produces two NSE_SYMBOL CompanyIdentifier rows (old symbol
valid_to = change date, new symbol valid_from = change date), never an
overwrite; multiple ISINs belonging to one real company (equity + bonds)
each get their own ISIN identifier row, all under the same `company_id`.

Idempotent: skips an ISIN that already has a company_identifiers row --
on a database already migrated by `scripts/migrate_company_dedup.py`,
this means every ISIN from the old, over-fragmented bootstrap is seen as
"already bootstrapped" and skipped, which is correct; this script only
bootstraps genuinely new ISINs going forward.
"""

from __future__ import annotations

import datetime as dt
import sys
import uuid
from pathlib import Path
from typing import cast

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import text  # noqa: E402

from ledgerlight.config.settings import load_settings  # noqa: E402
from ledgerlight.db.session import make_session_factory  # noqa: E402
from ledgerlight.ingestion.company_grouping import (  # noqa: E402
    IsinSegment,
    group_segments_into_companies,
)
from ledgerlight.knowledge.models import Company, CompanyIdentifier  # noqa: E402


def main() -> int:
    settings = load_settings()
    session_factory = make_session_factory(settings)

    with session_factory() as session:
        already_bootstrapped = {
            row[0]
            for row in session.execute(
                text(
                    "select distinct value from company_identifiers "
                    "where identifier_type = 'ISIN'"
                )
            ).all()
        }

        rows = session.execute(
            text(
                """
                select isin, symbol, source_id, min(trade_date) as seg_start,
                       max(trade_date) as seg_end,
                       (select id from price_bars pb2
                        where pb2.isin = pb.isin and pb2.symbol = pb.symbol
                        order by pb2.trade_date limit 1) as first_price_bar_id
                from price_bars pb
                where isin is not null and isin <> ''
                group by isin, symbol, source_id
                order by isin, seg_start
                """
            )
        ).all()

        by_isin: dict[str, list[IsinSegment]] = {}
        for isin, symbol, _source_id, seg_start, _seg_end, first_price_bar_id in rows:
            isin_str = str(isin)
            if isin_str in already_bootstrapped:
                continue
            by_isin.setdefault(isin_str, []).append(
                IsinSegment(
                    isin_str,
                    str(symbol),
                    cast(dt.date, seg_start),
                    cast(uuid.UUID, first_price_bar_id),
                )
            )

        skipped_already_bootstrapped = len(already_bootstrapped)
        groups = group_segments_into_companies(by_isin)

        companies_created = 0
        identifiers_created = 0

        for group in groups:
            company = Company(display_name=group.latest_symbol)
            session.add(company)
            session.flush()
            companies_created += 1

            for isin, (seg_start, first_price_bar_id) in group.isin_earliest.items():
                session.add(
                    CompanyIdentifier(
                        company_id=company.id,
                        identifier_type="ISIN",
                        value=isin,
                        valid_from=seg_start,
                        valid_to=None,
                        source_price_bar_id=first_price_bar_id,
                    )
                )
                identifiers_created += 1

            windows = group.symbol_windows
            for i, (symbol, seg_start, first_price_bar_id) in enumerate(windows):
                valid_to = windows[i + 1][1] if i + 1 < len(windows) else None
                session.add(
                    CompanyIdentifier(
                        company_id=company.id,
                        identifier_type="NSE_SYMBOL",
                        value=symbol,
                        valid_from=seg_start,
                        valid_to=valid_to,
                        source_price_bar_id=first_price_bar_id,
                    )
                )
                identifiers_created += 1

            if companies_created % 500 == 0:
                session.commit()

        session.commit()

    print(f"companies_created: {companies_created}")
    print(f"identifiers_created: {identifiers_created}")
    print(f"skipped (already bootstrapped): {skipped_already_bootstrapped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
