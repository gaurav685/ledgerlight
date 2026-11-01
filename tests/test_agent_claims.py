"""Tests for ledgerlight.agent.claims -- Phase 4 Sec4 DRAFT claim
building. Pure unit tests against the real Pydantic tool-output types,
no DB needed."""

from __future__ import annotations

import datetime as dt
import uuid

from ledgerlight.agent.claims import (
    claim_from_risk_score,
    claims_from_events,
    claims_from_outcomes_context,
    claims_from_timeline,
    entity_history_limitation_claim,
    standing_limitation_claims,
)
from ledgerlight.agent.tools import (
    EntityHistory,
    EventSummary,
    EvidenceSpanRef,
    OutcomesContext,
    RiskScoreResult,
    TimelineEntry,
)


def test_claims_from_events_carries_real_evidence_spans() -> None:
    event = EventSummary(
        event_id=uuid.uuid4(),
        event_type_code="AUD_RESIGN",
        event_time=dt.datetime(2020, 1, 1, tzinfo=dt.UTC),
        known_at=dt.datetime(2020, 1, 2, tzinfo=dt.UTC),
        severity="high",
        tier="VERIFIED",
        evidence=[
            EvidenceSpanRef(version_id=uuid.uuid4(), page_number=1, char_start=0, char_end=5)
        ],
    )
    drafts = claims_from_events([event])
    assert len(drafts) == 1
    assert drafts[0].claim_type == "event"
    assert len(drafts[0].evidence) == 1
    assert drafts[0].payload["tier"] == "VERIFIED"


def test_claims_from_events_produces_an_empty_evidence_claim_when_the_event_has_none() -> None:
    event = EventSummary(
        event_id=uuid.uuid4(),
        event_type_code="AUD_RESIGN",
        event_time=None,
        known_at=dt.datetime(2020, 1, 2, tzinfo=dt.UTC),
        severity="low",
        tier="CANDIDATE",
        evidence=[],
    )
    drafts = claims_from_events([event])
    assert drafts[0].evidence == []


def test_claims_from_timeline_skips_event_kind_entries() -> None:
    entries = [
        TimelineEntry(
            event_time=None,
            known_at=dt.datetime(2020, 1, 1, tzinfo=dt.UTC),
            kind="event",
            label="AUD_RESIGN",
            event_id=uuid.uuid4(),
        ),
        TimelineEntry(
            event_time=None,
            known_at=dt.datetime(2020, 2, 1, tzinfo=dt.UTC),
            kind="filing",
            label="sebi:order",
            version_id=uuid.uuid4(),
        ),
    ]
    drafts = claims_from_timeline(entries)
    assert len(drafts) == 1
    assert drafts[0].payload["kind"] == "filing"
    assert drafts[0].evidence == []


def test_claim_from_risk_score_is_produced_even_when_not_found() -> None:
    risk = RiskScoreResult(found=False, model_limitations="real limitations text")
    draft = claim_from_risk_score(risk)
    assert draft.claim_type == "risk_signal"
    assert draft.payload["found"] is False
    assert draft.payload["model_limitations"] == "real limitations text"
    assert draft.evidence == []


def test_claims_from_outcomes_context_covers_ibbi_sebi_and_ratings() -> None:
    from ledgerlight.agent.tools import OutcomeEvent, RatingHistoryEntry

    outcomes = OutcomesContext(
        ibbi_events=[
            OutcomeEvent(
                event_id=uuid.uuid4(),
                event_type_code="IBBI_CIRP_ADMISSION",
                event_time=None,
                known_at=dt.datetime(2020, 1, 1, tzinfo=dt.UTC),
                tier="VERIFIED",
                evidence=[],
            )
        ],
        sebi_events=[],
        rating_history=[
            RatingHistoryEntry(
                rating_symbol="CARE AA",
                ordinal=2,
                negative_outlook=False,
                known_at=dt.datetime(2020, 1, 1, tzinfo=dt.UTC),
                version_id=uuid.uuid4(),
                page_number=1,
                char_start=0,
                char_end=7,
            )
        ],
    )
    drafts = claims_from_outcomes_context(outcomes)
    assert sum(1 for d in drafts if d.claim_type == "event") == 1
    assert sum(1 for d in drafts if d.claim_type == "metric") == 1


def test_standing_limitation_claims_are_always_non_empty() -> None:
    drafts = standing_limitation_claims()
    assert len(drafts) == 4
    assert all(d.claim_type == "limitation" for d in drafts)
    assert all(d.evidence == [] for d in drafts)
    assert sum(1 for d in drafts if d.payload.get("is_disclaimer")) == 1


def test_entity_history_limitation_claim_is_none_when_tracked() -> None:
    history = EntityHistory(
        identifiers=[], linked_people_and_auditors=[], name_change_history_tracked=True
    )
    assert entity_history_limitation_claim(history) is None


def test_entity_history_limitation_claim_present_when_not_tracked() -> None:
    history = EntityHistory(identifiers=[], linked_people_and_auditors=[])
    claim = entity_history_limitation_claim(history)
    assert claim is not None
    assert claim.claim_type == "limitation"
