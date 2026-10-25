"""Bootstrap companies/company_identifiers from real bhavcopy data
(ISIN + NSE symbol history via price_bars) -- the ISIN is the stable
identifier; a symbol change over time produces two CompanyIdentifier
rows (old symbol valid_to = change date, new symbol valid_from = change
date), never an overwrite. Idempotent: skips an ISIN that already has a
company_identifiers row.
"""

from __future__ import annotations

import datetime as dt
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import cast

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import text  # noqa: E402

from ledgerlight.config.settings import load_settings  # noqa: E402
from ledgerlight.db.session import make_session_factory  # noqa: E402
from ledgerlight.knowledge.models import Company, CompanyIdentifier  # noqa: E402


@dataclass
class _Segment:
    symbol: str
    seg_start: dt.date
    first_price_bar_id: uuid.UUID


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

        segments = session.execute(
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

        by_isin: dict[str, list[_Segment]] = {}
        for isin, symbol, _source_id, seg_start, _seg_end, first_price_bar_id in segments:
            isin_str = str(isin)
            by_isin.setdefault(isin_str, []).append(
                _Segment(str(symbol), cast(dt.date, seg_start), cast(uuid.UUID, first_price_bar_id))
            )

        companies_created = 0
        identifiers_created = 0
        skipped_already_bootstrapped = 0

        for isin, segs in by_isin.items():
            if isin in already_bootstrapped:
                skipped_already_bootstrapped += 1
                continue

            segs.sort(key=lambda s: s.seg_start)
            latest_symbol = segs[-1].symbol

            company = Company(display_name=latest_symbol)
            session.add(company)
            session.flush()
            companies_created += 1

            session.add(
                CompanyIdentifier(
                    company_id=company.id,
                    identifier_type="ISIN",
                    value=isin,
                    valid_from=segs[0].seg_start,
                    valid_to=None,
                    source_price_bar_id=segs[0].first_price_bar_id,
                )
            )
            identifiers_created += 1

            for i, seg in enumerate(segs):
                valid_to = segs[i + 1].seg_start if i + 1 < len(segs) else None
                session.add(
                    CompanyIdentifier(
                        company_id=company.id,
                        identifier_type="NSE_SYMBOL",
                        value=seg.symbol,
                        valid_from=seg.seg_start,
                        valid_to=valid_to,
                        source_price_bar_id=seg.first_price_bar_id,
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
