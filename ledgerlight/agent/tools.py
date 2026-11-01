"""Phase 4 §3: the investigation agent's 7 read-only tools.

Every tool takes `as_of` and returns only data with `known_at <= as_of` --
the same point-in-time discipline this project has enforced since Phase 1
(`docs/knowledge/retrieval.md`, `ledgerlight.modelling.censoring`). No tool
writes, deletes, fetches from the network, or executes code -- every one
is a read-only SQLAlchemy query (or a read of an already-built local
index file) against the real database.

Every tool's output is wrapped in `ToolEnvelope`, marked `untrusted: True`
-- document and tool content is UNTRUSTED DATA per the brief's own ground
rules; nothing here is ever treated as an instruction.
"""

from __future__ import annotations

import datetime as dt
import uuid
from pathlib import Path
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict
from sqlalchemy import text
from sqlalchemy.orm import Session

from ledgerlight.knowledge.retrieval import BM25_INDEX_PATH, hybrid_search, load_bm25_index
from ledgerlight.modelling.rating_features import extract_rating_observations
from ledgerlight.modelling.scoring import get_score

MODEL_CARD_PATH = Path("docs/modelling/model-card.md")

T = TypeVar("T")


class ToolEnvelope(BaseModel, Generic[T]):
    """Every tool's real return value, wrapped. `untrusted` is always
    `True` -- a reminder, enforced by the type itself, that this is
    document/derived content, never an instruction, no matter which
    tool produced it or what it contains."""

    model_config = ConfigDict(frozen=True)

    untrusted: Literal[True] = True
    tool_name: str
    as_of: dt.date
    retrieved_at: dt.datetime
    data: T


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


# --- 1. search_filings -------------------------------------------------------


class FilingSearchHit(BaseModel):
    chunk_id: uuid.UUID
    version_id: uuid.UUID
    page_number: int
    char_start: int
    char_end: int
    text: str
    known_at: dt.datetime
    score: float


def search_filings(
    session: Session,
    query: str,
    as_of: dt.date,
    company_id: uuid.UUID | None = None,
    top_k: int = 10,
    bm25_index_path: Path = BM25_INDEX_PATH,
) -> ToolEnvelope[list[FilingSearchHit]]:
    """Real hybrid (BM25 + vector) retrieval, real company filter, real
    point-in-time filter (`ledgerlight.knowledge.retrieval.hybrid_search`
    already applies `known_at <= as_of` to the candidate pool before
    ranking -- not re-implemented here, reused directly)."""
    as_of_dt = dt.datetime.combine(as_of, dt.time.max, tzinfo=dt.UTC)
    bm25_index = load_bm25_index(bm25_index_path)
    scored = hybrid_search(session, bm25_index, query, as_of_dt, company_id, top_k=top_k)

    hits: list[FilingSearchHit] = []
    if scored:
        rows = session.execute(
            text(
                "SELECT id, version_id, page_number, char_start, char_end, text, known_at "
                "FROM chunks WHERE id = ANY(:ids)"
            ),
            {"ids": [c.chunk_id for c in scored]},
        ).all()
        by_id = {row[0]: row for row in rows}
        score_by_id = {c.chunk_id: c.score for c in scored}
        for chunk_id in (c.chunk_id for c in scored):
            row = by_id.get(chunk_id)
            if row is None:
                continue
            hits.append(
                FilingSearchHit(
                    chunk_id=row[0],
                    version_id=row[1],
                    page_number=row[2],
                    char_start=row[3],
                    char_end=row[4],
                    text=row[5],
                    known_at=row[6],
                    score=score_by_id[chunk_id],
                )
            )

    return ToolEnvelope(tool_name="search_filings", as_of=as_of, retrieved_at=_now(), data=hits)


# --- 2. get_evidence ----------------------------------------------------------


class EvidenceSpan(BaseModel):
    version_id: uuid.UUID
    page_number: int
    char_start: int
    char_end: int
    text: str
    known_at: dt.datetime


def get_evidence(
    session: Session,
    version_id: uuid.UUID,
    page_number: int,
    char_start: int,
    char_end: int,
    as_of: dt.date,
) -> ToolEnvelope[EvidenceSpan | None]:
    """Exact raw_text span by version/page/offsets -- the real string the
    citation claims to resolve against, never re-extracted or
    paraphrased. Returns `None` (not a fabricated span) if the page
    doesn't exist, the offsets are out of range, or the page's own
    `known_at` is after `as_of`."""
    row = session.execute(
        text(
            "SELECT dp.raw_text, dv.known_at FROM document_pages dp "
            "JOIN document_versions dv ON dv.id = dp.version_id "
            "WHERE dp.version_id = :version_id AND dp.page_number = :page_number"
        ),
        {"version_id": version_id, "page_number": page_number},
    ).one_or_none()

    data: EvidenceSpan | None = None
    if row is not None:
        raw_text, known_at = row[0], row[1]
        if known_at.date() <= as_of and 0 <= char_start < char_end <= len(raw_text):
            data = EvidenceSpan(
                version_id=version_id,
                page_number=page_number,
                char_start=char_start,
                char_end=char_end,
                text=raw_text[char_start:char_end],
                known_at=known_at,
            )

    return ToolEnvelope(tool_name="get_evidence", as_of=as_of, retrieved_at=_now(), data=data)


# --- 3. get_events -------------------------------------------------------------


class EvidenceSpanRef(BaseModel):
    version_id: uuid.UUID
    page_number: int
    char_start: int
    char_end: int


class EventSummary(BaseModel):
    event_id: uuid.UUID
    event_type_code: str
    event_time: dt.datetime | None
    known_at: dt.datetime
    severity: str
    tier: str  # "VERIFIED" | "CANDIDATE" (events.status, normalized)
    evidence: list[EvidenceSpanRef]


_TIER_BY_STATUS = {"verified": "VERIFIED"}


def get_events(
    session: Session,
    company_id: uuid.UUID,
    as_of: dt.date,
    event_type_code: str | None = None,
) -> ToolEnvelope[list[EventSummary]]:
    """Real governance red-flag events for this company (the
    `taxonomy-v1.0.yaml` red-flag taxonomy -- excludes the separate
    `outcomes-1.0` taxonomy version that `get_outcomes_context` covers),
    with each event's real tier (`events.status`, normalized to
    VERIFIED/CANDIDATE -- `rejected`/`needs_review` are excluded, same
    as `ledgerlight.modelling.seed_governance_features`) and its real
    evidence spans."""
    as_of_end = dt.datetime.combine(as_of, dt.time.max, tzinfo=dt.UTC)
    rows = session.execute(
        text(
            """
            SELECT e.id, et.code, e.event_time, e.known_at, e.severity, e.status
            FROM events e
            JOIN event_types et ON et.id = e.event_type_id
            JOIN taxonomy_versions tv ON tv.id = et.taxonomy_version_id
            WHERE e.company_id = :company_id
              AND tv.version != 'outcomes-1.0'
              AND e.status IN ('candidate', 'verified')
              AND e.known_at <= :as_of_end
              AND (CAST(:event_type_code AS TEXT) IS NULL OR et.code = :event_type_code)
            ORDER BY e.known_at
            """
        ),
        {
            "company_id": company_id,
            "as_of_end": as_of_end,
            "event_type_code": event_type_code,
        },
    ).all()

    events: list[EventSummary] = []
    if rows:
        event_ids = [row[0] for row in rows]
        field_rows = session.execute(
            text(
                "SELECT event_id, evidence_version_id, evidence_page, "
                "evidence_char_start, evidence_char_end FROM event_fields "
                "WHERE event_id = ANY(:ids)"
            ),
            {"ids": event_ids},
        ).all()
        evidence_by_event: dict[uuid.UUID, list[EvidenceSpanRef]] = {}
        for field_row in field_rows:
            evidence_by_event.setdefault(field_row[0], []).append(
                EvidenceSpanRef(
                    version_id=field_row[1],
                    page_number=field_row[2],
                    char_start=field_row[3],
                    char_end=field_row[4],
                )
            )
        for row in rows:
            events.append(
                EventSummary(
                    event_id=row[0],
                    event_type_code=row[1],
                    event_time=row[2],
                    known_at=row[3],
                    severity=row[4],
                    tier=_TIER_BY_STATUS.get(row[5], "CANDIDATE"),
                    evidence=evidence_by_event.get(row[0], []),
                )
            )

    return ToolEnvelope(tool_name="get_events", as_of=as_of, retrieved_at=_now(), data=events)


# --- 4. get_entity_history -----------------------------------------------------


class IdentifierHistoryEntry(BaseModel):
    identifier_type: str
    value: str
    valid_from: dt.date | None
    valid_to: dt.date | None


class LinkedEntity(BaseModel):
    entity_id: uuid.UUID
    entity_type: str
    display_name: str
    first_known_at: dt.datetime


class EntityHistory(BaseModel):
    identifiers: list[IdentifierHistoryEntry]
    linked_people_and_auditors: list[LinkedEntity]
    name_change_history_tracked: bool = False
    limitation: str = (
        "Company display_name is a single current value in this project's schema -- "
        "no real name-change history is tracked. Only identifier history "
        "(ISIN/NSE_SYMBOL/BSE_CODE/CIN validity windows) is available."
    )


def get_entity_history(
    session: Session, company_id: uuid.UUID, as_of: dt.date
) -> ToolEnvelope[EntityHistory]:
    """Real identifier validity history (point-in-time: `valid_from <=
    as_of`) plus real linked people/audit firms/rating agencies --
    entities whose mentions were found in this company's own real,
    auto-linked filings, known as of `as_of`. Company name-change
    history is NOT tracked in this project's schema -- disclosed via
    `EntityHistory.limitation`, never silently omitted."""
    identifier_rows = session.execute(
        text(
            "SELECT identifier_type, value, valid_from, valid_to FROM company_identifiers "
            "WHERE company_id = :company_id AND (valid_from IS NULL OR valid_from <= :as_of) "
            "ORDER BY identifier_type, valid_from"
        ),
        {"company_id": company_id, "as_of": as_of},
    ).all()
    identifiers = [
        IdentifierHistoryEntry(
            identifier_type=row[0], value=row[1], valid_from=row[2], valid_to=row[3]
        )
        for row in identifier_rows
    ]

    as_of_end = dt.datetime.combine(as_of, dt.time.max, tzinfo=dt.UTC)
    entity_rows = session.execute(
        text(
            """
            SELECT DISTINCT en.id, en.entity_type, en.display_name, min(dv.known_at) OVER (
                PARTITION BY en.id
            ) AS first_known_at
            FROM mentions m
            JOIN filings f ON f.version_id = m.version_id
            JOIN document_versions dv ON dv.id = m.version_id
            JOIN entity_links el ON el.mention_id = m.id AND el.status = 'active'
            JOIN entities en ON en.id = el.entity_id
            WHERE f.company_id = :company_id
              AND dv.known_at <= :as_of_end
              AND en.entity_type IN ('person', 'audit_firm', 'rating_agency')
            ORDER BY en.id
            """
        ),
        {"company_id": company_id, "as_of_end": as_of_end},
    ).all()
    linked = [
        LinkedEntity(
            entity_id=row[0], entity_type=row[1], display_name=row[2], first_known_at=row[3]
        )
        for row in entity_rows
    ]

    return ToolEnvelope(
        tool_name="get_entity_history",
        as_of=as_of,
        retrieved_at=_now(),
        data=EntityHistory(identifiers=identifiers, linked_people_and_auditors=linked),
    )


# --- 5. get_timeline -----------------------------------------------------------


class TimelineEntry(BaseModel):
    event_time: dt.datetime | None
    known_at: dt.datetime
    kind: Literal["event", "filing"]
    label: str
    tier: str | None = None
    event_id: uuid.UUID | None = None
    version_id: uuid.UUID | None = None


def get_timeline(
    session: Session, company_id: uuid.UUID, as_of: dt.date
) -> ToolEnvelope[list[TimelineEntry]]:
    """Real events and real filings for this company, ordered by
    `event_time` (falling back to `known_at` when `event_time` is
    unknown), with `event_time` and `known_at` always kept as two
    distinct real fields -- never collapsed into one date."""
    events_envelope = get_events(session, company_id, as_of)
    entries = [
        TimelineEntry(
            event_time=event.event_time,
            known_at=event.known_at,
            kind="event",
            label=event.event_type_code,
            tier=event.tier,
            event_id=event.event_id,
        )
        for event in events_envelope.data
    ]

    as_of_end = dt.datetime.combine(as_of, dt.time.max, tzinfo=dt.UTC)
    filing_rows = session.execute(
        text(
            """
            SELECT dv.id, dv.known_at, dv.published_at, d.document_type, d.source_id
            FROM filings f
            JOIN document_versions dv ON dv.id = f.version_id
            JOIN documents d ON d.id = dv.document_id
            WHERE f.company_id = :company_id AND dv.known_at <= :as_of_end
            ORDER BY dv.known_at
            """
        ),
        {"company_id": company_id, "as_of_end": as_of_end},
    ).all()
    for row in filing_rows:
        entries.append(
            TimelineEntry(
                event_time=row[2],
                known_at=row[1],
                kind="filing",
                label=f"{row[4]}:{row[3]}",
                version_id=row[0],
            )
        )

    entries.sort(key=lambda e: e.event_time or e.known_at)
    return ToolEnvelope(tool_name="get_timeline", as_of=as_of, retrieved_at=_now(), data=entries)


# --- 6. get_risk_score ---------------------------------------------------------


class RiskScoreResult(BaseModel):
    found: bool
    raw_probability: float | None = None
    calibrated_probability: float | None = None
    percentile: float | None = None
    top_shap_contributors: list[object] | None = None
    score_as_of: dt.date | None = None
    model_limitations: str


def _read_model_card_intended_use(model_card_path: Path) -> str:
    if not model_card_path.exists():
        return "model-card.md not found -- real limitations could not be read."
    text_content = model_card_path.read_text(encoding="utf-8")
    marker = "## Intended use"
    start = text_content.find(marker)
    if start == -1:
        return "model-card.md found but has no 'Intended use' section."
    end = text_content.find("\n## ", start + len(marker))
    section = text_content[start : end if end != -1 else None]
    return section.strip()


def get_risk_score(
    session: Session,
    company_id: uuid.UUID,
    as_of: dt.date,
    model_name: str = "primary-risk-lightgbm",
    model_version: str = "1.0",
    model_card_path: Path = MODEL_CARD_PATH,
) -> ToolEnvelope[RiskScoreResult]:
    """Real score via `ledgerlight.modelling.scoring.get_score` (already
    point-in-time correct: never returns a score computed after
    `as_of`), with the real model-card "Intended use" section (including
    the real "statistically inconclusive" finding, if present) read live
    -- never a duplicated, driftable copy of that text."""
    retrieved = get_score(session, company_id, as_of, model_name, model_version)
    limitations = _read_model_card_intended_use(model_card_path)

    if retrieved is None:
        data = RiskScoreResult(found=False, model_limitations=limitations)
    else:
        data = RiskScoreResult(
            found=True,
            raw_probability=retrieved.raw_probability,
            calibrated_probability=retrieved.calibrated_probability,
            percentile=retrieved.percentile,
            top_shap_contributors=retrieved.top_shap_contributors,
            score_as_of=retrieved.as_of,
            model_limitations=limitations,
        )

    return ToolEnvelope(tool_name="get_risk_score", as_of=as_of, retrieved_at=_now(), data=data)


# --- 7. get_outcomes_context ---------------------------------------------------


class OutcomeEvent(BaseModel):
    event_id: uuid.UUID
    event_type_code: str
    event_time: dt.datetime | None
    known_at: dt.datetime
    tier: str
    evidence: list[EvidenceSpanRef]


class RatingHistoryEntry(BaseModel):
    rating_symbol: str
    ordinal: int
    negative_outlook: bool
    known_at: dt.datetime
    version_id: uuid.UUID
    page_number: int
    char_start: int
    char_end: int


class OutcomesContext(BaseModel):
    ibbi_events: list[OutcomeEvent]
    sebi_events: list[OutcomeEvent]
    rating_history: list[RatingHistoryEntry]


_OUTCOME_EVENT_TYPE_CODES = {
    "ibbi_events": "IBBI_CIRP_ADMISSION",
    "sebi_events": "SEBI_ORDER_AGAINST_COMPANY",
}


def get_outcomes_context(
    session: Session, company_id: uuid.UUID, as_of: dt.date
) -> ToolEnvelope[OutcomesContext]:
    """Real, auto-linked-only IBBI admission events, SEBI order events,
    and CARE rating history for this company, all filtered to
    `known_at <= as_of`. Reuses
    `ledgerlight.modelling.rating_features.extract_rating_observations`
    for ratings rather than re-deriving it."""
    as_of_end = dt.datetime.combine(as_of, dt.time.max, tzinfo=dt.UTC)

    def _outcome_events(event_type_code: str) -> list[OutcomeEvent]:
        rows = session.execute(
            text(
                """
                SELECT e.id, e.event_time, e.known_at, e.status
                FROM events e
                JOIN event_types et ON et.id = e.event_type_id
                JOIN taxonomy_versions tv ON tv.id = et.taxonomy_version_id
                WHERE e.company_id = :company_id AND et.code = :code
                  AND tv.version = 'outcomes-1.0' AND e.known_at <= :as_of_end
                ORDER BY e.known_at
                """
            ),
            {"company_id": company_id, "code": event_type_code, "as_of_end": as_of_end},
        ).all()
        results: list[OutcomeEvent] = []
        for row in rows:
            field_rows = session.execute(
                text(
                    "SELECT evidence_version_id, evidence_page, evidence_char_start, "
                    "evidence_char_end FROM event_fields WHERE event_id = :event_id"
                ),
                {"event_id": row[0]},
            ).all()
            evidence = [
                EvidenceSpanRef(
                    version_id=field_row[0],
                    page_number=field_row[1],
                    char_start=field_row[2],
                    char_end=field_row[3],
                )
                for field_row in field_rows
            ]
            results.append(
                OutcomeEvent(
                    event_id=row[0],
                    event_type_code=event_type_code,
                    event_time=row[1],
                    known_at=row[2],
                    tier=_TIER_BY_STATUS.get(row[3], "CANDIDATE"),
                    evidence=evidence,
                )
            )
        return results

    rating_observations = [
        RatingHistoryEntry(
            rating_symbol=obs.rating_symbol,
            ordinal=obs.ordinal,
            negative_outlook=obs.negative_outlook,
            known_at=obs.known_at,
            version_id=obs.version_id,
            page_number=obs.page_number,
            char_start=obs.char_start,
            char_end=obs.char_end,
        )
        for obs in extract_rating_observations(session, company_id)
        if obs.known_at.date() <= as_of
    ]

    data = OutcomesContext(
        ibbi_events=_outcome_events(_OUTCOME_EVENT_TYPE_CODES["ibbi_events"]),
        sebi_events=_outcome_events(_OUTCOME_EVENT_TYPE_CODES["sebi_events"]),
        rating_history=rating_observations,
    )
    return ToolEnvelope(
        tool_name="get_outcomes_context", as_of=as_of, retrieved_at=_now(), data=data
    )
