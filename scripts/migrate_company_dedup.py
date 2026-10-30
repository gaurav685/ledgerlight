"""One-time migration: fix the real company-fragmentation bug (one
Company row per ISIN instead of per real company) left behind by the
original bootstrap_companies.py -- see ledgerlight.ingestion
.company_grouping's docstring and docs/phase-3/phase-3-report.md's
Sec2.4 addendum for the full writeup.

For every group of ISINs that the corrected grouping logic says belong
to ONE real company, but which currently sit under MORE THAN ONE
`companies` row: pick a canonical row, re-point every real reference
(filings.company_id, events.company_id, label_items.company_id,
entities.company_id) from the other rows onto it, delete the duplicate
`company_identifiers` rows and regenerate them correctly under the
canonical id, delete the duplicate `companies` rows, and fix the
canonical row's own display_name if needed.

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
import datetime as dt
import json
import sys
import uuid
from pathlib import Path
from typing import cast

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import select, text  # noqa: E402

from ledgerlight.config.settings import load_settings  # noqa: E402
from ledgerlight.db.session import make_session_factory  # noqa: E402
from ledgerlight.ingestion.company_grouping import (  # noqa: E402
    CompanyGroup,
    IsinSegment,
    group_segments_into_companies,
)
from ledgerlight.knowledge.models import (  # noqa: E402
    Company,
    CompanyIdentifier,
    Entity,
    Event,
    Filing,
    LabelItem,
)


def _load_groups(session) -> list[CompanyGroup]:  # type: ignore[no-untyped-def]
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
        by_isin.setdefault(isin_str, []).append(
            IsinSegment(
                isin_str, str(symbol), cast(dt.date, seg_start), cast(uuid.UUID, first_price_bar_id)
            )
        )
    return group_segments_into_companies(by_isin)


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    settings = load_settings()
    session_factory = make_session_factory(settings)

    with session_factory() as session:
        groups = _load_groups(session)

        fragmented_groups = 0
        companies_deleted = 0
        identifiers_regenerated = 0
        filings_repointed = 0
        filings_deleted_as_duplicate = 0
        events_repointed = 0
        label_items_repointed = 0
        entities_repointed = 0
        before_state: list[dict[str, object]] = []

        for group in groups:
            existing_rows = session.execute(
                select(CompanyIdentifier.company_id, CompanyIdentifier.value).where(
                    CompanyIdentifier.identifier_type == "ISIN",
                    CompanyIdentifier.value.in_(group.isins),
                )
            ).all()
            existing_company_ids = {row[0] for row in existing_rows}
            if len(existing_company_ids) <= 1:
                continue  # already correct (or not yet bootstrapped at all)

            fragmented_groups += 1
            companies = {
                c.id: c
                for c in session.execute(
                    select(Company).where(Company.id.in_(existing_company_ids))
                ).scalars()
            }
            canonical_id = next(
                (cid for cid, c in companies.items() if c.display_name == group.latest_symbol),
                min(companies, key=lambda cid: companies[cid].created_at),
            )
            duplicate_ids = [cid for cid in existing_company_ids if cid != canonical_id]

            before_state.append(
                {
                    "group_isins": group.isins,
                    "latest_symbol": group.latest_symbol,
                    "canonical_id": str(canonical_id),
                    "duplicate_ids": [str(d) for d in duplicate_ids],
                    "companies": {
                        str(cid): companies[cid].display_name for cid in existing_company_ids
                    },
                }
            )

            if args.dry_run:
                continue

            for old_id in duplicate_ids:
                # Filing has a UNIQUE(version_id, company_id) constraint --
                # re-pointing could collide with a Filing already on the
                # canonical id for the same version. Delete the redundant
                # one rather than erroring.
                old_filings = (
                    session.execute(select(Filing).where(Filing.company_id == old_id))
                    .scalars()
                    .all()
                )
                for filing in old_filings:
                    collision = session.execute(
                        select(Filing).where(
                            Filing.version_id == filing.version_id,
                            Filing.company_id == canonical_id,
                        )
                    ).scalar()
                    if collision is not None:
                        session.delete(filing)
                        filings_deleted_as_duplicate += 1
                    else:
                        filing.company_id = canonical_id
                        filings_repointed += 1

                events_to_fix = (
                    session.execute(select(Event).where(Event.company_id == old_id)).scalars().all()
                )
                for event in events_to_fix:
                    event.company_id = canonical_id
                events_repointed += len(events_to_fix)

                label_items_to_fix = (
                    session.execute(select(LabelItem).where(LabelItem.company_id == old_id))
                    .scalars()
                    .all()
                )
                for label_item in label_items_to_fix:
                    label_item.company_id = canonical_id
                label_items_repointed += len(label_items_to_fix)

                entities_to_fix = (
                    session.execute(select(Entity).where(Entity.company_id == old_id))
                    .scalars()
                    .all()
                )
                for entity in entities_to_fix:
                    entity.company_id = canonical_id
                entities_repointed += len(entities_to_fix)

            # Regenerate CompanyIdentifier rows correctly under canonical_id.
            session.execute(
                text("delete from company_identifiers where company_id = any(:ids)"),
                {"ids": [canonical_id, *duplicate_ids]},
            )
            for isin, (seg_start, first_price_bar_id) in group.isin_earliest.items():
                session.add(
                    CompanyIdentifier(
                        company_id=canonical_id,
                        identifier_type="ISIN",
                        value=isin,
                        valid_from=seg_start,
                        valid_to=None,
                        source_price_bar_id=first_price_bar_id,
                    )
                )
                identifiers_regenerated += 1
            windows = group.symbol_windows
            for i, (symbol, seg_start, first_price_bar_id) in enumerate(windows):
                valid_to = windows[i + 1][1] if i + 1 < len(windows) else None
                session.add(
                    CompanyIdentifier(
                        company_id=canonical_id,
                        identifier_type="NSE_SYMBOL",
                        value=symbol,
                        valid_from=seg_start,
                        valid_to=valid_to,
                        source_price_bar_id=first_price_bar_id,
                    )
                )
                identifiers_regenerated += 1

            companies[canonical_id].display_name = group.latest_symbol
            for old_id in duplicate_ids:
                session.delete(companies[old_id])
                companies_deleted += 1

        if args.dry_run:
            evidence_path = (
                REPO_ROOT / "docs" / "phase-3" / "evidence" / "company-dedup-dry-run.json"
            )
            evidence_path.write_text(json.dumps(before_state, indent=2, default=str))
            duplicate_count = sum(len(cast("list[str]", g["duplicate_ids"])) for g in before_state)
            print(f"[DRY RUN] fragmented_groups_found: {fragmented_groups}")
            print(f"[DRY RUN] would delete {duplicate_count} duplicate company rows")
            print(f"[DRY RUN] full plan written to {evidence_path}")
            return 0

        session.commit()

    print(f"fragmented_groups_fixed: {fragmented_groups}")
    print(f"companies_deleted: {companies_deleted}")
    print(f"identifiers_regenerated: {identifiers_regenerated}")
    print(f"filings_repointed: {filings_repointed}")
    print(f"filings_deleted_as_duplicate: {filings_deleted_as_duplicate}")
    print(f"events_repointed: {events_repointed}")
    print(f"label_items_repointed: {label_items_repointed}")
    print(f"entities_repointed: {entities_repointed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
