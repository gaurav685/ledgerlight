"""Splits label_items into dev/validation/test by company and time --
never randomly, and never splitting one company's items across sets
(that would leak information from test into training). A label_item
whose document isn't yet linked to a company (see
ledgerlight.knowledge.filings) is grouped by source_id instead, so items
from the same source still stay together.

Groups are ordered by their earliest known_at and assigned to dev/
validation/test by cumulative proportion (default 60/20/20) -- the test
set is always the chronologically LATEST group(s), consistent with
point-in-time evaluation (never evaluating on a trading day the
"development" work could have seen in hindsight).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from ledgerlight.db.models import Document, DocumentVersion
from ledgerlight.knowledge.models import Filing, LabelItem

DEV_FRACTION = 0.6
VALIDATION_FRACTION = 0.2
# remaining ~0.2 is TEST


@dataclass
class SplitStats:
    groups: int = 0
    dev: int = 0
    validation: int = 0
    test: int = 0


def split_labels(session: Session) -> SplitStats:
    rows = session.execute(
        select(LabelItem, DocumentVersion.known_at, Document.source_id)
        .join(DocumentVersion, DocumentVersion.id == LabelItem.version_id)
        .join(Document, Document.id == DocumentVersion.document_id)
    ).all()

    filings_by_version = {
        version_id: company_id
        for version_id, company_id in session.execute(
            select(Filing.version_id, Filing.company_id)
        ).all()
    }

    groups: dict[str, list[tuple[LabelItem, dt.datetime]]] = {}
    for item, known_at, source_id in rows:
        company_id = filings_by_version.get(item.version_id)
        item.company_id = company_id
        group_key = str(company_id) if company_id is not None else f"nocompany:{source_id}"
        groups.setdefault(group_key, []).append((item, known_at))

    group_order = sorted(groups.items(), key=lambda kv: min(k[1] for k in kv[1]))

    total_items = sum(len(items) for _, items in group_order)
    dev_cutoff = total_items * DEV_FRACTION
    validation_cutoff = total_items * (DEV_FRACTION + VALIDATION_FRACTION)

    stats = SplitStats(groups=len(group_order))
    cumulative = 0
    for _group_key, items in group_order:
        group_midpoint = cumulative + len(items) / 2
        if group_midpoint < dev_cutoff:
            split = "dev"
        elif group_midpoint < validation_cutoff:
            split = "validation"
        else:
            split = "test"

        for item, _known_at in items:
            item.split = split
            if split == "dev":
                stats.dev += 1
            elif split == "validation":
                stats.validation += 1
            else:
                stats.test += 1
        cumulative += len(items)

    session.commit()
    return stats
