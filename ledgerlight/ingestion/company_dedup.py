"""Shared logic for finding and merging duplicate `Company` rows that
real ISIN/symbol co-occurrence in `price_bars` says belong to ONE real
company. Originally written as a one-time migration
(`scripts/migrate_company_dedup.py`) for the 422-company fragmentation
bug found in Phase 3 Sec2.4. Reused here because the SAME class of bug
can recur every time `scripts/bootstrap_companies.py` bootstraps a
never-before-seen ISIN that happens to share an NSE symbol with an
ALREADY-bootstrapped company -- the new-ISIN grouping pass has no way
to know about an existing company's claim on that symbol, so it creates
a second, duplicate Company instead of attaching to the first. Real
case found 2026-10-31: re-running bootstrap to pick up a backlog of
1,819 never-bootstrapped companies created 94 such duplicates (e.g.
8KMILES/SECURKLOUD -- a real rename already correctly captured by the
existing company; the new ISIN's own grouping knew only the old,
pre-rename symbol name).

`bootstrap_companies.py` now calls `merge_fragmented_groups` at the end
of every run, so this class of bug is self-healing on each bootstrap
run rather than requiring a manual follow-up migration every time.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass, field
from typing import cast

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from ledgerlight.ingestion.company_grouping import (
    CompanyGroup,
    IsinSegment,
    group_segments_into_companies,
)
from ledgerlight.knowledge.models import (
    Company,
    CompanyIdentifier,
    Entity,
    Event,
    Filing,
    LabelItem,
)


@dataclass
class MergeStats:
    fragmented_groups: int = 0
    companies_deleted: int = 0
    identifiers_regenerated: int = 0
    filings_repointed: int = 0
    filings_deleted_as_duplicate: int = 0
    events_repointed: int = 0
    label_items_repointed: int = 0
    entities_repointed: int = 0
    before_state: list[dict[str, object]] = field(default_factory=list)


def load_groups(session: Session) -> list[CompanyGroup]:
    """Real ISIN/symbol grouping derived fresh from ALL of price_bars --
    not scoped to any particular bootstrap run -- so it reflects every
    real rename/co-occurrence regardless of when each ISIN was first
    bootstrapped."""
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


def find_fragmented_groups(
    session: Session, groups: list[CompanyGroup]
) -> list[tuple[CompanyGroup, set[uuid.UUID]]]:
    """A group is fragmented if its ISINs currently resolve to MORE THAN
    ONE real Company row. Read-only -- safe to call for a dry-run."""
    fragmented = []
    for group in groups:
        existing_rows = session.execute(
            select(CompanyIdentifier.company_id, CompanyIdentifier.value).where(
                CompanyIdentifier.identifier_type == "ISIN",
                CompanyIdentifier.value.in_(group.isins),
            )
        ).all()
        existing_company_ids = {row[0] for row in existing_rows}
        if len(existing_company_ids) > 1:
            fragmented.append((group, existing_company_ids))
    return fragmented


def merge_fragmented_groups(
    session: Session, fragmented: list[tuple[CompanyGroup, set[uuid.UUID]]]
) -> MergeStats:
    """Applies the real merge for every fragmented group found by
    `find_fragmented_groups`: pick a canonical Company (the one whose
    display_name already matches the group's real latest symbol, else
    the oldest), re-point every real reference onto it, regenerate
    CompanyIdentifier rows fresh under the canonical id, delete the
    duplicates. Caller commits."""
    stats = MergeStats()

    for group, existing_company_ids in fragmented:
        stats.fragmented_groups += 1
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

        stats.before_state.append(
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

        for old_id in duplicate_ids:
            old_filings = (
                session.execute(select(Filing).where(Filing.company_id == old_id)).scalars().all()
            )
            for filing in old_filings:
                collision = session.execute(
                    select(Filing).where(
                        Filing.version_id == filing.version_id, Filing.company_id == canonical_id
                    )
                ).scalar()
                if collision is not None:
                    session.delete(filing)
                    stats.filings_deleted_as_duplicate += 1
                else:
                    filing.company_id = canonical_id
                    stats.filings_repointed += 1

            events_to_fix = (
                session.execute(select(Event).where(Event.company_id == old_id)).scalars().all()
            )
            for event in events_to_fix:
                event.company_id = canonical_id
            stats.events_repointed += len(events_to_fix)

            label_items_to_fix = (
                session.execute(select(LabelItem).where(LabelItem.company_id == old_id))
                .scalars()
                .all()
            )
            for label_item in label_items_to_fix:
                label_item.company_id = canonical_id
            stats.label_items_repointed += len(label_items_to_fix)

            entities_to_fix = (
                session.execute(select(Entity).where(Entity.company_id == old_id)).scalars().all()
            )
            for entity in entities_to_fix:
                entity.company_id = canonical_id
            stats.entities_repointed += len(entities_to_fix)

        # Regenerate CompanyIdentifier rows correctly under canonical_id.
        # identifier_window_corrections.identifier_id is ON DELETE SET NULL
        # (and denormalizes identifier_type/value) precisely so this never
        # fails or silently destroys that audit trail.
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
            stats.identifiers_regenerated += 1
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
            stats.identifiers_regenerated += 1

        companies[canonical_id].display_name = group.latest_symbol
        for old_id in duplicate_ids:
            session.delete(companies[old_id])
            stats.companies_deleted += 1

    return stats
