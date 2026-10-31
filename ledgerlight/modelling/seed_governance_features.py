"""SEED track governance features for Phase 3 Sec4.3 -- "descriptive
only" per the brief, for the 15 SEED-track companies. Reuses the real
Phase 2 `Event`/`EventField` rows from the red-flag taxonomy
(`taxonomy-v1.0.yaml`), excluding `GUIDANCE_MISS` (that is Sec5's own
feature, guidance credibility, built separately).

Every count here is tagged by its real tier: VERIFIED (`Event.status ==
'verified'`) or CANDIDATE (anything else). As of this build (2026-10-31),
real project-wide counts show every governance event still at
`status='candidate'` -- Phase 1 Sec1.5 already found no event type
clears the gold-reliability bar for promotion to VERIFIED. This module
reports that plainly rather than hiding it: a near-all-CANDIDATE result
is the real, current state of this corpus's governance signal, not a
bug in this feature code.

A second, real, disclosed caveat: an event whose only evidence comes
from a non-"reliable" source (e.g. a company's own investor-relations
site, not SEBI/IBBI/CARE/NSE) gets `known_at = retrieved_at` per
`ledgerlight.db.temporal`'s deliberate, conservative policy -- NOT the
document's own real-world publish date. Every such document in this
project was fetched within one narrow acquisition window, so a
trailing-12-month COUNT built from these clusters as a one-time step
function pinned to that acquisition date, not a genuine temporal
signal. Real example found while building this: Vakrangee's real 2017
auditor-resignation announcements (`published_at` 2017-12-31) all carry
`known_at` from 2026-10-25 (this project's own fetch date) because the
source is `vakrangee.in`, not one of the four reliable sources. Pledge
level/change "from structured numbers" (per the brief's own wording) is
NOT built here: no structured pledge-level data source exists in this
project's real corpus (see docs/data/source-inventory.md) -- disclosed
as a real gap, not fabricated from the text-derived PLEDGE_UP event
candidates."""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

# GUIDANCE_MISS excluded deliberately -- that is Sec5's own feature.
GOVERNANCE_EVENT_CODES: list[str] = [
    "AUD_RESIGN",
    "PLEDGE_UP",
    "KMP_EXIT",
    "ID_EXIT",
    "RATING_ACT",
    "RESULT_DELAY",
    "AUDIT_QUAL",
    "FORENSIC",
    "RPT_GROWTH",
]


@dataclass
class GovernanceEventRecord:
    code: str
    known_at: dt.datetime
    status: str  # 'candidate' | 'verified' | 'rejected' | 'needs_review'


def load_governance_events(session: Session, company_id: uuid.UUID) -> list[GovernanceEventRecord]:
    """Real events for one company, excluding GUIDANCE_MISS and any
    `rejected`/`needs_review` status (those are explicitly not usable
    signal -- a rejected candidate is a known false positive, and
    needs_review is unresolved, neither belongs in a feature)."""
    rows = session.execute(
        text(
            """
            SELECT et.code, e.known_at, e.status
            FROM events e
            JOIN event_types et ON et.id = e.event_type_id
            JOIN taxonomy_versions tv ON tv.id = et.taxonomy_version_id
            WHERE e.company_id = :company_id
              AND tv.version != 'outcomes-1.0'
              AND et.code != 'GUIDANCE_MISS'
              AND e.status IN ('candidate', 'verified')
            ORDER BY e.known_at
            """
        ),
        {"company_id": company_id},
    ).all()
    return [GovernanceEventRecord(code=row[0], known_at=row[1], status=row[2]) for row in rows]


def compute_governance_features(
    events: list[GovernanceEventRecord], as_of: dt.date
) -> dict[str, int]:
    """Counts per real governance event code, trailing 12 months,
    known as of `as_of`, split by tier. `None` is never produced here
    -- 0 is the correct, real answer for "no such event known in this
    window," not an absence of information (unlike the rating
    features, where "never rated" genuinely differs from "rated and
    stable")."""
    window_start = as_of - dt.timedelta(days=365)
    known = [e for e in events if e.known_at.date() <= as_of]
    in_window = [e for e in known if e.known_at.date() > window_start]

    values: dict[str, int] = {}
    for code in GOVERNANCE_EVENT_CODES:
        candidate_count = sum(1 for e in in_window if e.code == code and e.status == "candidate")
        verified_count = sum(1 for e in in_window if e.code == code and e.status == "verified")
        values[f"{code.lower()}_candidate_count_12m"] = candidate_count
        values[f"{code.lower()}_verified_count_12m"] = verified_count
    values["governance_candidate_total_12m"] = sum(
        v for k, v in values.items() if k.endswith("_candidate_count_12m")
    )
    values["governance_verified_total_12m"] = sum(
        v for k, v in values.items() if k.endswith("_verified_count_12m")
    )
    return values
