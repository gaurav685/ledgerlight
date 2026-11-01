"""Phase 4 §7: human review workflow -- routing rules, reason codes,
the review CLI's real backend operations, the append-only audit, and
the immutable-event-version feedback loop.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

from ledgerlight.agent.models import Claim, Dossier, Investigation, ReviewDecisionAudit, ReviewTask

HIGH_SEVERITY_FINDING = "high_severity_finding"
CONFLICTING_EVIDENCE = "conflicting_evidence"
LOW_CONFIDENCE_EXTRACTION = "low_confidence_extraction"
VERIFICATION_FAILED = "verification_failed"
CANDIDATE_TIER_MAJORITY = "candidate_tier_majority"
BUDGET_EXCEEDED = "budget_exceeded"
SEEDED_QC = "seeded_qc"

REASON_CODES: dict[str, str] = {
    HIGH_SEVERITY_FINDING: "A real event with severity='high' appears in the dossier.",
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
}

LOW_CONFIDENCE_THRESHOLD = 0.7
DEFAULT_REVIEW_PRIORITY = 0
HIGH_REVIEW_PRIORITY = 10


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
    session: Session, investigation: Investigation, dossier: Dossier, claims: list[Claim]
) -> list[RoutingDecision]:
    """Real routing decisions for one real investigation's finished
    dossier -- every rule the brief lists, checked against real data,
    never assumed. More than one reason can fire; all are returned."""
    decisions: list[RoutingDecision] = []

    if dossier.sections.get("conflicting_evidence"):
        decisions.append(RoutingDecision(CONFLICTING_EVIDENCE, HIGH_REVIEW_PRIORITY))

    if investigation.final_status == "NEEDS_REVIEW":
        if investigation.failure_reason and "budget_exceeded" in investigation.failure_reason:
            decisions.append(RoutingDecision(BUDGET_EXCEEDED, HIGH_REVIEW_PRIORITY))
        else:
            decisions.append(RoutingDecision(VERIFICATION_FAILED, HIGH_REVIEW_PRIORITY))

    event_claims = [c for c in claims if c.claim_type == "event"]
    if any(c.payload.get("severity") == "high" for c in event_claims):
        decisions.append(RoutingDecision(HIGH_SEVERITY_FINDING, HIGH_REVIEW_PRIORITY))

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
) -> list[ReviewTask]:
    decisions = determine_routing(session, investigation, dossier, claims)

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
