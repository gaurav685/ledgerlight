"""Real, query-derived "verified coverage" for the primary outcome
(`IBBI_CIRP_ADMISSION` OR `RATING_DOWNGRADE_D`) -- per the user's
explicit condition (2026-10-31): restrict outcome windows and test
folds to periods where BOTH IBBI and rating-default (CARE) sources
have VERIFIED coverage, as recorded in `docs/modelling/data-quality.md`.
Observations outside that coverage are CENSORED, not labelled negative.

"Verified coverage" for a source means a real company has at least one
real, auto-linked `Filing` row for that source -- i.e. this project
actually checked that source for that company and found (or did not
find) something, as opposed to never having checked at all. A company
only belongs in the restricted universe if BOTH sources were checked
for it; the real company-level intersection is computed fresh from the
database every time this is called, never hardcoded, so it can never
silently go stale as new Filing rows are added.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session


@dataclass
class VerifiedCoverage:
    window_start: dt.date
    window_end: dt.date
    company_ids: list[uuid.UUID]
    company_names: list[str]
    ibbi_known_at_range: tuple[dt.datetime, dt.datetime]
    care_known_at_range: tuple[dt.datetime, dt.datetime]


def compute_verified_coverage(session: Session) -> VerifiedCoverage:
    ibbi_range = session.execute(
        text(
            "SELECT min(dv.known_at), max(dv.known_at) FROM document_versions dv "
            "JOIN documents d ON d.id = dv.document_id WHERE d.source_id = 'ibbi'"
        )
    ).one()
    care_range = session.execute(
        text(
            "SELECT min(dv.known_at), max(dv.known_at) FROM document_versions dv "
            "JOIN documents d ON d.id = dv.document_id WHERE d.source_id = 'care'"
        )
    ).one()

    window_start = max(ibbi_range[0], care_range[0]).date()
    window_end = min(ibbi_range[1], care_range[1]).date()

    rows = session.execute(
        text(
            """
            SELECT co.id, co.display_name FROM companies co WHERE co.id IN (
                SELECT f.company_id FROM filings f
                JOIN document_versions dv ON dv.id = f.version_id
                JOIN documents d ON d.id = dv.document_id WHERE d.source_id = 'care'
                INTERSECT
                SELECT f.company_id FROM filings f
                JOIN document_versions dv ON dv.id = f.version_id
                JOIN documents d ON d.id = dv.document_id WHERE d.source_id = 'ibbi'
            )
            ORDER BY co.display_name
            """
        )
    ).all()

    return VerifiedCoverage(
        window_start=window_start,
        window_end=window_end,
        company_ids=[row[0] for row in rows],
        company_names=[row[1] for row in rows],
        ibbi_known_at_range=(ibbi_range[0], ibbi_range[1]),
        care_known_at_range=(care_range[0], care_range[1]),
    )
