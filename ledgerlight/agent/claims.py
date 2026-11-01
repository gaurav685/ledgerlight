"""Phase 4 §2/§4 DRAFT stage: builds real, structured `ClaimDraft`s from
the real tool envelopes GATHER/TIMELINE already collected. Every claim
with a real document citation carries a real, non-empty `evidence` list
(the exact shape the §5 verifier resolves against real
`document_pages.raw_text`).

Two claim types -- `risk_signal` and `limitation` -- are a disclosed
exception: they describe this project's own model output or its own
real, documented coverage gaps (e.g. "exchange sources are BLOCKED",
"the Phase 3 risk model is statistically inconclusive"), not a fact
extracted from one specific company document span. They carry
`evidence: []` and a `source` field in their payload instead (a real
project document path, or "ledgerlight.modelling.scoring.get_score" for
a real score lookup) -- the §5 verifier's citation-resolution check is
scoped to claims with a non-empty `evidence` list, and does not apply
to these two types for that reason, stated here rather than silently
special-cased inside the verifier."""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass, field

from ledgerlight.agent.tools import (
    EntityHistory,
    EventSummary,
    OutcomesContext,
    RiskScoreResult,
    TimelineEntry,
)

NO_GUIDANCE_DATA_LIMITATION = (
    "No real management-issued forward-guidance statements exist anywhere in this "
    "project's corpus (0 found after a real search of 4,759 pages) -- see "
    "docs/modelling/guidance-extraction-assessment.md."
)
BLOCKED_EXCHANGE_SOURCES_LIMITATION = (
    "NSE and BSE exchange-announcement sources are BLOCKED for this project "
    "(data/manifests/sources.yaml) -- no real company announcements from either "
    "exchange are in this corpus."
)
PARTIAL_IBBI_COVERAGE_LIMITATION = (
    "The real IBBI full-universe discovery crawl was honestly stopped, not completed "
    "(~2.75% of the target universe covered) -- see docs/modelling/data-quality.md. "
    "IBBI admission events are only available for companies with a real, auto-linked "
    "IBBI Filing; absence of an IBBI event is not proof no real admission occurred."
)


@dataclass
class EvidenceRef:
    document_version_id: uuid.UUID
    page_number: int
    char_start: int
    char_end: int

    def to_json(self) -> dict[str, object]:
        return {
            "document_version_id": str(self.document_version_id),
            "page_number": self.page_number,
            "char_start": self.char_start,
            "char_end": self.char_end,
        }


@dataclass
class ClaimDraft:
    claim_type: str  # event | timeline_entry | metric | risk_signal | limitation
    payload: dict[str, object]
    evidence: list[EvidenceRef] = field(default_factory=list)

    def evidence_json(self) -> list[object]:
        return [e.to_json() for e in self.evidence]


def claims_from_events(events: list[EventSummary]) -> list[ClaimDraft]:
    """One real `event` claim per real governance red-flag event, with
    every one of its real evidence spans -- an event with zero evidence
    spans produces a claim with `evidence: []`, which the verifier must
    then fail (a real event claim with no citation is a real defect to
    surface, never silently dropped before VERIFY)."""
    drafts: list[ClaimDraft] = []
    for event in events:
        drafts.append(
            ClaimDraft(
                claim_type="event",
                payload={
                    "event_id": str(event.event_id),
                    "event_type_code": event.event_type_code,
                    "event_time": event.event_time.isoformat() if event.event_time else None,
                    "known_at": event.known_at.isoformat(),
                    "severity": event.severity,
                    "tier": event.tier,
                },
                evidence=[
                    EvidenceRef(span.version_id, span.page_number, span.char_start, span.char_end)
                    for span in event.evidence
                ],
            )
        )
    return drafts


def claims_from_timeline(entries: list[TimelineEntry]) -> list[ClaimDraft]:
    """One real `timeline_entry` claim per real ordered filing entry
    (`kind == "filing"`). Event-kind timeline entries are deliberately
    skipped here -- `claims_from_events`/`claims_from_outcomes_context`
    already produce a real `event` claim with real evidence spans for
    the same underlying event, so repeating it as a second,
    span-less `timeline_entry` claim would be redundant. A filing
    entry records that a real document was known as of a date, not an
    extracted statement -- there is no specific real text span to cite
    for "this document exists", so it carries `evidence: []` and the
    real `version_id` in its own payload instead (the same disclosed
    exemption as `risk_signal`/`limitation`). `event_time` and
    `known_at` are kept as two distinct real fields -- never
    collapsed, per §4's explicit requirement."""
    drafts: list[ClaimDraft] = []
    for entry in entries:
        if entry.kind != "filing":
            continue
        drafts.append(
            ClaimDraft(
                claim_type="timeline_entry",
                payload={
                    "kind": entry.kind,
                    "label": entry.label,
                    "event_time": entry.event_time.isoformat() if entry.event_time else None,
                    "known_at": entry.known_at.isoformat(),
                    "version_id": str(entry.version_id) if entry.version_id else None,
                    "source": "document existence, not an extracted statement",
                },
                evidence=[],
            )
        )
    return drafts


def claims_from_outcomes_context(outcomes: OutcomesContext) -> list[ClaimDraft]:
    """Real `event` claims for IBBI/SEBI outcome events, and real
    `metric` claims for each real rating observation."""
    drafts: list[ClaimDraft] = []
    for event in [*outcomes.ibbi_events, *outcomes.sebi_events]:
        drafts.append(
            ClaimDraft(
                claim_type="event",
                payload={
                    "event_id": str(event.event_id),
                    "event_type_code": event.event_type_code,
                    "event_time": event.event_time.isoformat() if event.event_time else None,
                    "known_at": event.known_at.isoformat(),
                    "tier": event.tier,
                },
                evidence=[
                    EvidenceRef(span.version_id, span.page_number, span.char_start, span.char_end)
                    for span in event.evidence
                ],
            )
        )
    for rating in outcomes.rating_history:
        drafts.append(
            ClaimDraft(
                claim_type="metric",
                payload={
                    "name": "care_rating",
                    "value": rating.rating_symbol,
                    "unit": "CARE_rating_symbol",
                    "known_at": rating.known_at.isoformat(),
                    "negative_outlook": rating.negative_outlook,
                },
                evidence=[
                    EvidenceRef(
                        rating.version_id, rating.page_number, rating.char_start, rating.char_end
                    )
                ],
            )
        )
    return drafts


def claim_from_risk_score(risk: RiskScoreResult) -> ClaimDraft:
    """The one real `risk_signal` claim per investigation -- always
    produced, even when `risk.found` is False (a real "no score
    available" is itself real, reportable information, never silently
    omitted)."""
    return ClaimDraft(
        claim_type="risk_signal",
        payload={
            "found": risk.found,
            "raw_probability": risk.raw_probability,
            "calibrated_probability": risk.calibrated_probability,
            "percentile": risk.percentile,
            "top_shap_contributors": risk.top_shap_contributors,
            "score_as_of": risk.score_as_of.isoformat() if risk.score_as_of else None,
            "model_limitations": risk.model_limitations,
            "source": "ledgerlight.modelling.scoring.get_score",
        },
        evidence=[],
    )


def standing_limitation_claims() -> list[ClaimDraft]:
    """The real, standing, project-level limitation claims every
    dossier must disclose -- not derived per-investigation, since they
    are true of this project's own corpus, not of any one company."""
    return [
        ClaimDraft(
            claim_type="limitation",
            payload={"text": text, "source": source},
            evidence=[],
        )
        for text, source in (
            (NO_GUIDANCE_DATA_LIMITATION, "docs/modelling/guidance-extraction-assessment.md"),
            (BLOCKED_EXCHANGE_SOURCES_LIMITATION, "data/manifests/sources.yaml"),
            (PARTIAL_IBBI_COVERAGE_LIMITATION, "docs/modelling/data-quality.md"),
        )
    ]


def entity_history_limitation_claim(entity_history: EntityHistory) -> ClaimDraft | None:
    if entity_history.name_change_history_tracked:
        return None
    return ClaimDraft(
        claim_type="limitation",
        payload={"text": entity_history.limitation, "source": "ledgerlight.agent.tools"},
        evidence=[],
    )


def investigation_timestamp_claim(as_of: dt.date) -> ClaimDraft:
    """A real `metric` claim recording the investigation's own
    point-in-time anchor, so the rendered dossier can state it without
    any claim needing to reach outside its own claim set."""
    return ClaimDraft(
        claim_type="metric",
        payload={"name": "investigation_as_of", "value": as_of.isoformat(), "unit": "date"},
        evidence=[],
    )
