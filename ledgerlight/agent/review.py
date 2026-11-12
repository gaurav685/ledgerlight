"""Phase 4 §7: human review workflow -- routing rules, reason codes,
the review CLI's real backend operations, the append-only audit, and
the immutable-event-version feedback loop.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from ledgerlight.agent.models import Claim, Dossier, Investigation, ReviewDecisionAudit, ReviewTask

HIGH_SEVERITY_FINDING = "high_severity_finding"
CONFLICTING_EVIDENCE = "conflicting_evidence"
LOW_CONFIDENCE_EXTRACTION = "low_confidence_extraction"
VERIFICATION_FAILED = "verification_failed"
CANDIDATE_TIER_MAJORITY = "candidate_tier_majority"
BUDGET_EXCEEDED = "budget_exceeded"
SEEDED_QC = "seeded_qc"
REPAIR_REMOVED_HIGH_SEVERITY = "repair_removed_high_severity"
REPAIR_EMPTIED_SECTION = "repair_emptied_section"

REASON_CODES: dict[str, str] = {
    HIGH_SEVERITY_FINDING: (
        "A real high-severity finding appears in the dossier -- a real event with "
        "severity='high' (e.g. an IBBI_CIRP_ADMISSION or SEBI_ORDER_AGAINST_COMPANY "
        "outcome event), or a real default-grade (CARE rating symbol 'D') metric claim."
    ),
    CONFLICTING_EVIDENCE: (
        "The verifier found two or more real claims of the same event type with "
        "different known_at dates -- presented together, never silently resolved."
    ),
    LOW_CONFIDENCE_EXTRACTION: (
        "A real extracted field feeding a claim has confidence below the real threshold."
    ),
    VERIFICATION_FAILED: (
        "The investigation's real final_status is NEEDS_REVIEW -- a verification check "
        "failed, or REPAIR exhausted its rounds, or the state machine stopped short."
    ),
    CANDIDATE_TIER_MAJORITY: (
        "More than half of the real event claims in this dossier are CANDIDATE tier, "
        "not VERIFIED."
    ),
    BUDGET_EXCEEDED: "A real budget limit (steps/wall time/tool calls/tokens/cost) was exceeded.",
    SEEDED_QC: (
        "A deliberately flawed dossier injected by qc-seed (ledgerlight.agent.qc_seed) to "
        "measure real reviewer catch rate -- never a real finding; excluded from every "
        "other real statistic."
    ),
    REPAIR_REMOVED_HIGH_SEVERITY: (
        "REPAIR removed a real claim that would itself have been a high-severity "
        "finding (by the same definition as HIGH_SEVERITY_FINDING above) -- a human "
        "should confirm the dossier's silence on it is correct, not a verifier miss."
    ),
    REPAIR_EMPTIED_SECTION: (
        "REPAIR removed every real claim that would have populated a section "
        "('chronology', 'findings', or 'risk_signals'), leaving it empty in the final "
        "dossier -- a human should confirm there is genuinely nothing to report, not "
        "that real content was silently dropped."
    ),
}

LOW_CONFIDENCE_THRESHOLD = 0.7
DEFAULT_REVIEW_PRIORITY = 0
HIGH_REVIEW_PRIORITY = 10

DEFAULT_GRADE_RATING_SYMBOLS = frozenset({"D"})
"""The real CARE rating symbol(s) that mean "in default" -- the worst
real rating this corpus's own RATING_ORDINAL assigns (see
ledgerlight.modelling.rating_features). A metric claim naming this
symbol is always a high-severity finding, by the same real-world
meaning the risk model's own outcome taxonomy already assigns it
(RATING_DOWNGRADE_D is a PRIMARY outcome type)."""

# Which claim_type(s) a dossier section's own sentences are built from
# (ledgerlight.agent.render.render_offline) -- used to tell "REPAIR
# removed something that would have populated this section" apart from
# "this section was always going to be empty."
_SECTION_SOURCE_CLAIM_TYPES: dict[str, frozenset[str]] = {
    "chronology": frozenset({"timeline_entry"}),
    "findings": frozenset({"event", "metric"}),
    "risk_signals": frozenset({"risk_signal"}),
}


def _is_high_severity(claim: Claim) -> bool:
    """A claim real enough to independently justify the
    HIGH_SEVERITY_FINDING routing reason -- an event with
    severity='high', or a default-grade rating metric claim."""
    if claim.claim_type == "event":
        return claim.payload.get("severity") == "high"
    if claim.claim_type == "metric" and claim.payload.get("name") == "care_rating":
        return claim.payload.get("value") in DEFAULT_GRADE_RATING_SYMBOLS
    return False


@dataclass
class RoutingDecision:
    reason_code: str
    priority: int


def _confidence_for_event_claims(
    session: Session, event_claim_ids: list[uuid.UUID]
) -> dict[uuid.UUID, float]:
    if not event_claim_ids:
        return {}
    rows = session.execute(
        text(
            "SELECT c.id, min(ef.confidence) FROM claims c "
            "JOIN event_fields ef ON ef.event_id = (c.payload->>'event_id')::uuid "
            "WHERE c.id = ANY(:ids) GROUP BY c.id"
        ),
        {"ids": event_claim_ids},
    ).all()
    return {row[0]: float(row[1]) for row in rows}


def determine_routing(
    session: Session,
    investigation: Investigation,
    dossier: Dossier,
    claims: list[Claim],
    failed_claims: list[Claim] | None = None,
) -> list[RoutingDecision]:
    """Real routing decisions for one real investigation's finished
    dossier -- every rule the brief lists, checked against real data,
    never assumed. More than one reason can fire; all are returned.

    `claims` is the real, ACTIVE (rendered) claim set -- every existing
    check here is deliberately scoped to "what the final dossier
    actually shows", never to claims that failed verification.
    `failed_claims` (Phase 6 Correction 2 Sec2, optional for backward
    compatibility with any other caller) is the real set REPAIR
    removed -- used ONLY by the two REPAIR-specific checks below, which
    are about what got silently dropped, not what's shown."""
    decisions: list[RoutingDecision] = []
    failed_claims = failed_claims or []

    if dossier.sections.get("conflicting_evidence"):
        decisions.append(RoutingDecision(CONFLICTING_EVIDENCE, HIGH_REVIEW_PRIORITY))

    if investigation.final_status == "NEEDS_REVIEW":
        if investigation.failure_reason and "budget_exceeded" in investigation.failure_reason:
            decisions.append(RoutingDecision(BUDGET_EXCEEDED, HIGH_REVIEW_PRIORITY))
        else:
            decisions.append(RoutingDecision(VERIFICATION_FAILED, HIGH_REVIEW_PRIORITY))

    event_claims = [c for c in claims if c.claim_type == "event"]
    if any(_is_high_severity(c) for c in claims):
        decisions.append(RoutingDecision(HIGH_SEVERITY_FINDING, HIGH_REVIEW_PRIORITY))

    if any(_is_high_severity(c) for c in failed_claims):
        decisions.append(RoutingDecision(REPAIR_REMOVED_HIGH_SEVERITY, HIGH_REVIEW_PRIORITY))

    for section, source_types in _SECTION_SOURCE_CLAIM_TYPES.items():
        if dossier.sections.get(section):
            continue  # not empty -- nothing was lost
        if any(c.claim_type in source_types for c in failed_claims):
            decisions.append(RoutingDecision(REPAIR_EMPTIED_SECTION, HIGH_REVIEW_PRIORITY))
            break  # one task covers the whole dossier, not one per section

    if event_claims:
        candidate_count = sum(1 for c in event_claims if c.payload.get("tier") == "CANDIDATE")
        if candidate_count > len(event_claims) / 2:
            decisions.append(RoutingDecision(CANDIDATE_TIER_MAJORITY, DEFAULT_REVIEW_PRIORITY))

    confidences = _confidence_for_event_claims(session, [c.id for c in event_claims])
    if any(v < LOW_CONFIDENCE_THRESHOLD for v in confidences.values()):
        decisions.append(RoutingDecision(LOW_CONFIDENCE_EXTRACTION, DEFAULT_REVIEW_PRIORITY))

    return decisions


def create_review_tasks(
    session: Session,
    investigation: Investigation,
    dossier: Dossier,
    claims: list[Claim],
    failed_claims: list[Claim] | None = None,
) -> list[ReviewTask]:
    decisions = determine_routing(session, investigation, dossier, claims, failed_claims)

    tasks: list[ReviewTask] = []
    for decision in decisions:
        task = ReviewTask(
            dossier_id=dossier.id,
            reason_code=decision.reason_code,
            priority=decision.priority,
            status="open",
        )
        session.add(task)
        tasks.append(task)
    session.flush()
    return tasks


def list_open_tasks(session: Session, limit: int | None = None) -> list[ReviewTask]:
    """The real open review queue -- highest real priority first, then
    oldest first, the same ordering a human reviewer would want to
    work through."""
    query = (
        select(ReviewTask)
        .where(ReviewTask.status == "open")
        .order_by(ReviewTask.priority.desc(), ReviewTask.created_at)
    )
    if limit is not None:
        query = query.limit(limit)
    return list(session.scalars(query).all())


def get_task_dossier(session: Session, review_task_id: uuid.UUID) -> Dossier | None:
    """The real dossier a review task is about, or `None` if this task
    references a single claim rather than a whole dossier (the CHECK
    constraint on `review_tasks` allows either)."""
    task = session.get(ReviewTask, review_task_id)
    if task is None or task.dossier_id is None:
        return None
    return session.get(Dossier, task.dossier_id)


def record_decision(
    session: Session,
    review_task_id: uuid.UUID,
    decision: str,
    reviewer: str,
    notes: str | None = None,
) -> ReviewTask:
    """Records a real reviewer decision (approve | approve_with_edits |
    reject | escalate) and appends to the real, append-only
    `review_decisions_audit` -- never edits a prior audit row."""
    task = session.get(ReviewTask, review_task_id)
    assert task is not None, "review_task_id does not exist"
    before = {"status": task.status, "decision": task.decision}

    task.decision = decision
    task.decision_notes = notes
    task.decided_at = dt.datetime.now(dt.UTC)
    task.status = "closed"
    task.assignee = reviewer

    after = {"status": task.status, "decision": task.decision}
    session.add(
        ReviewDecisionAudit(
            review_task_id=task.id,
            actor=reviewer,
            action="decided",
            before=before,
            after=after,
        )
    )
    session.commit()
    return task


def apply_event_feedback(
    session: Session,
    event_id: uuid.UUID,
    new_status: str,
    reviewer: str,
    review_task_id: uuid.UUID | None = None,
    notes: str | None = None,
) -> None:
    """Phase 4 §7 feedback loop: a reviewer decision creates a NEW,
    immutable `EventVersion` row -- `events.status` itself is never
    mutated in place. This never touches the frozen Phase 1/2 test
    split: no column here references `label_items` or any gold-label
    table."""
    from ledgerlight.agent.models import EventVersion

    session.add(
        EventVersion(
            event_id=event_id,
            status=new_status,
            reviewer=reviewer,
            review_task_id=review_task_id,
            notes=notes,
        )
    )
    session.commit()
