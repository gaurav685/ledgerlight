"""Tests for ledgerlight.agent.review -- Phase 4 Sec7. determine_routing
is tested against the real db_session fixture (read-only, no commits).
record_decision/apply_event_feedback commit internally, so they use a
real, independent session with explicit cleanup (same reason as
test_agent_state_machine.py)."""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from ledgerlight.agent.models import Claim, Dossier, EventVersion, Investigation, ReviewTask
from ledgerlight.agent.review import (
    BUDGET_EXCEEDED,
    CANDIDATE_TIER_MAJORITY,
    CONFLICTING_EVIDENCE,
    HIGH_SEVERITY_FINDING,
    LOW_CONFIDENCE_EXTRACTION,
    REPAIR_EMPTIED_SECTION,
    REPAIR_REMOVED_HIGH_SEVERITY,
    VERIFICATION_FAILED,
    apply_event_feedback,
    create_review_tasks,
    determine_routing,
    get_task_dossier,
    list_open_tasks,
    record_decision,
)
from ledgerlight.knowledge.models import Company, Event, EventType

pytestmark = pytest.mark.integration


def _investigation(
    final_status: str | None = None, failure_reason: str | None = None
) -> Investigation:
    return Investigation(
        id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        as_of=dt.date(2020, 1, 1),
        requested_by="test",
        budget_config={},
        usage={},
        final_status=final_status,
        failure_reason=failure_reason,
    )


def _dossier(investigation_id: uuid.UUID, sections: dict[str, list[str]] | None = None) -> Dossier:
    return Dossier(
        investigation_id=investigation_id,
        version=1,
        status="FINALISED",
        sections=sections or {},
        claim_id_map={},
        renderer_name="offline_template",
        renderer_version="1",
    )


def _event_claim(**payload: object) -> Claim:
    return Claim(investigation_id=uuid.uuid4(), claim_type="event", payload=payload, evidence=[])


def _metric_claim(**payload: object) -> Claim:
    return Claim(investigation_id=uuid.uuid4(), claim_type="metric", payload=payload, evidence=[])


# --- determine_routing (read-only) --------------------------------------------


def test_determine_routing_flags_budget_exceeded(db_session: Session) -> None:
    investigation = _investigation(
        final_status="NEEDS_REVIEW", failure_reason="budget_exceeded: steps 5 >= max_steps 5"
    )
    dossier = _dossier(uuid.uuid4())
    decisions = determine_routing(db_session, investigation, dossier, [])
    assert any(d.reason_code == BUDGET_EXCEEDED for d in decisions)


def test_determine_routing_flags_verification_failed_when_not_budget(db_session: Session) -> None:
    investigation = _investigation(
        final_status="NEEDS_REVIEW", failure_reason="verification_failed after 2 repair round(s)"
    )
    dossier = _dossier(uuid.uuid4())
    decisions = determine_routing(db_session, investigation, dossier, [])
    assert any(d.reason_code == VERIFICATION_FAILED for d in decisions)
    assert not any(d.reason_code == BUDGET_EXCEEDED for d in decisions)


def test_determine_routing_flags_high_severity_finding(db_session: Session) -> None:
    investigation = _investigation()
    dossier = _dossier(uuid.uuid4())
    claims = [_event_claim(severity="high", tier="VERIFIED")]
    decisions = determine_routing(db_session, investigation, dossier, claims)
    assert any(d.reason_code == HIGH_SEVERITY_FINDING for d in decisions)


def test_determine_routing_flags_candidate_tier_majority(db_session: Session) -> None:
    investigation = _investigation()
    dossier = _dossier(uuid.uuid4())
    claims = [
        _event_claim(severity="low", tier="CANDIDATE"),
        _event_claim(severity="low", tier="CANDIDATE"),
        _event_claim(severity="low", tier="VERIFIED"),
    ]
    decisions = determine_routing(db_session, investigation, dossier, claims)
    assert any(d.reason_code == CANDIDATE_TIER_MAJORITY for d in decisions)


def test_determine_routing_does_not_flag_candidate_majority_when_mostly_verified(
    db_session: Session,
) -> None:
    investigation = _investigation()
    dossier = _dossier(uuid.uuid4())
    claims = [
        _event_claim(severity="low", tier="VERIFIED"),
        _event_claim(severity="low", tier="VERIFIED"),
        _event_claim(severity="low", tier="CANDIDATE"),
    ]
    decisions = determine_routing(db_session, investigation, dossier, claims)
    assert not any(d.reason_code == CANDIDATE_TIER_MAJORITY for d in decisions)


def test_determine_routing_flags_conflicting_evidence_from_dossier_section(
    db_session: Session,
) -> None:
    investigation = _investigation()
    dossier = _dossier(uuid.uuid4(), sections={"conflicting_evidence": ["Conflicting evidence."]})
    decisions = determine_routing(db_session, investigation, dossier, [])
    assert any(d.reason_code == CONFLICTING_EVIDENCE for d in decisions)


def test_determine_routing_empty_when_nothing_real_triggers(db_session: Session) -> None:
    investigation = _investigation()
    dossier = _dossier(uuid.uuid4())
    decisions = determine_routing(db_session, investigation, dossier, [])
    assert decisions == []


# --- Phase 6 Correction 2 Sec2: high-severity now sees metric claims too -----


def test_determine_routing_flags_high_severity_for_a_default_grade_rating(
    db_session: Session,
) -> None:
    """The real THERMAX/FRETAIL-shaped finding: a CARE 'D' rating is a
    metric claim, not an event claim -- had no severity field at all
    under the old rule, so a real default-grade finding never routed."""
    investigation = _investigation()
    dossier = _dossier(uuid.uuid4())
    claims = [_metric_claim(name="care_rating", value="D", unit="CARE_rating_symbol")]
    decisions = determine_routing(db_session, investigation, dossier, claims)
    assert any(d.reason_code == HIGH_SEVERITY_FINDING for d in decisions)


def test_determine_routing_does_not_flag_a_non_default_rating(db_session: Session) -> None:
    investigation = _investigation()
    dossier = _dossier(uuid.uuid4())
    claims = [_metric_claim(name="care_rating", value="AA-", unit="CARE_rating_symbol")]
    decisions = determine_routing(db_session, investigation, dossier, claims)
    assert not any(d.reason_code == HIGH_SEVERITY_FINDING for d in decisions)


def test_determine_routing_flags_high_severity_for_an_outcome_event_with_real_severity(
    db_session: Session,
) -> None:
    """The real IBBI_CIRP_ADMISSION/SEBI_ORDER_AGAINST_COMPANY finding:
    claims_from_outcomes_context's own event claims now carry the real
    Event.severity field through to the payload (it never used to)."""
    investigation = _investigation()
    dossier = _dossier(uuid.uuid4())
    claims = [_event_claim(event_type_code="IBBI_CIRP_ADMISSION", tier="VERIFIED", severity="high")]
    decisions = determine_routing(db_session, investigation, dossier, claims)
    assert any(d.reason_code == HIGH_SEVERITY_FINDING for d in decisions)


# --- Phase 6 Correction 2 Sec2: REPAIR-removed claims now route too ----------


def test_determine_routing_flags_repair_removed_high_severity(db_session: Session) -> None:
    investigation = _investigation()
    dossier = _dossier(uuid.uuid4())
    failed = [_metric_claim(name="care_rating", value="D", unit="CARE_rating_symbol")]
    decisions = determine_routing(db_session, investigation, dossier, [], failed)
    assert any(d.reason_code == REPAIR_REMOVED_HIGH_SEVERITY for d in decisions)


def test_determine_routing_does_not_flag_repair_removed_for_a_low_severity_failure(
    db_session: Session,
) -> None:
    investigation = _investigation()
    dossier = _dossier(uuid.uuid4())
    failed = [_event_claim(severity="low", tier="CANDIDATE")]
    decisions = determine_routing(db_session, investigation, dossier, [], failed)
    assert not any(d.reason_code == REPAIR_REMOVED_HIGH_SEVERITY for d in decisions)


def test_determine_routing_flags_repair_emptied_findings_section(db_session: Session) -> None:
    investigation = _investigation()
    # "findings" is empty in the real, final dossier -- but a real
    # event claim existed and was removed by REPAIR.
    dossier = _dossier(uuid.uuid4(), sections={"findings": []})
    failed = [_event_claim(severity="low", tier="CANDIDATE")]
    decisions = determine_routing(db_session, investigation, dossier, [], failed)
    assert any(d.reason_code == REPAIR_EMPTIED_SECTION for d in decisions)


def test_determine_routing_does_not_flag_repair_emptied_when_section_has_content(
    db_session: Session,
) -> None:
    investigation = _investigation()
    dossier = _dossier(uuid.uuid4(), sections={"findings": ["A real finding."]})
    failed = [_event_claim(severity="low", tier="CANDIDATE")]
    decisions = determine_routing(db_session, investigation, dossier, [], failed)
    assert not any(d.reason_code == REPAIR_EMPTIED_SECTION for d in decisions)


def test_determine_routing_does_not_flag_repair_emptied_for_an_unrelated_failed_claim(
    db_session: Session,
) -> None:
    """A section genuinely always empty (no real claim type that would
    have populated it ever failed) must not be flagged -- only a
    failure of the SPECIFIC claim type that section is built from."""
    investigation = _investigation()
    # "findings" has real content (excluded from the empty-section
    # check); "risk_signals" is genuinely empty, but the only failed
    # claim is an "event" (feeds "findings"), not a "risk_signal".
    dossier = _dossier(uuid.uuid4(), sections={"findings": ["A real finding."], "risk_signals": []})
    failed = [_event_claim(severity="low", tier="CANDIDATE")]
    decisions = determine_routing(db_session, investigation, dossier, [], failed)
    assert not any(d.reason_code == REPAIR_EMPTIED_SECTION for d in decisions)


def test_determine_routing_emptied_section_is_one_task_not_one_per_section(
    db_session: Session,
) -> None:
    investigation = _investigation()
    dossier = _dossier(uuid.uuid4(), sections={"findings": [], "chronology": []})
    failed = [
        _event_claim(severity="low", tier="CANDIDATE"),
        Claim(investigation_id=uuid.uuid4(), claim_type="timeline_entry", payload={}, evidence=[]),
    ]
    decisions = determine_routing(db_session, investigation, dossier, [], failed)
    assert sum(1 for d in decisions if d.reason_code == REPAIR_EMPTIED_SECTION) == 1


# --- create_review_tasks / record_decision / apply_event_feedback (real commits) --


@pytest.fixture
def real_session() -> Iterator[Session]:
    from pathlib import Path

    from ledgerlight.config.settings import Settings
    from ledgerlight.db.session import make_session_factory

    repo_root = Path(__file__).resolve().parent.parent
    try:
        settings = Settings(_env_file=str(repo_root / ".env"))  # type: ignore[call-arg]
    except Exception as exc:
        pytest.skip(f"could not load real .env for integration test: {exc}")

    session_factory = make_session_factory(settings)
    try:
        session = session_factory()
    except Exception as exc:
        pytest.skip(f"Postgres not reachable (is the Docker stack up?): {exc}")

    created: dict[str, list[uuid.UUID]] = {"investigations": [], "companies": [], "events": []}
    session.info["created"] = created
    try:
        yield session
    finally:
        _cleanup(session, created)
        session.close()


def _cleanup(session: Session, created: dict[str, list[uuid.UUID]]) -> None:
    investigation_ids = created["investigations"]
    if investigation_ids:
        session.execute(
            text(
                "DELETE FROM review_decisions_audit WHERE review_task_id IN "
                "(SELECT id FROM review_tasks WHERE dossier_id IN "
                "(SELECT id FROM dossiers WHERE investigation_id = ANY(:ids)) "
                "OR claim_id IN (SELECT id FROM claims WHERE investigation_id = ANY(:ids)))"
            ),
            {"ids": investigation_ids},
        )
        session.execute(
            text(
                "DELETE FROM review_tasks WHERE dossier_id IN "
                "(SELECT id FROM dossiers WHERE investigation_id = ANY(:ids)) "
                "OR claim_id IN (SELECT id FROM claims WHERE investigation_id = ANY(:ids))"
            ),
            {"ids": investigation_ids},
        )
        session.execute(
            text("DELETE FROM dossiers WHERE investigation_id = ANY(:ids)"),
            {"ids": investigation_ids},
        )
        session.execute(
            text("DELETE FROM claims WHERE investigation_id = ANY(:ids)"),
            {"ids": investigation_ids},
        )
        session.execute(
            text("DELETE FROM investigations WHERE id = ANY(:ids)"), {"ids": investigation_ids}
        )
    event_ids = created["events"]
    if event_ids:
        session.execute(
            text("DELETE FROM event_versions WHERE event_id = ANY(:ids)"), {"ids": event_ids}
        )
        session.execute(text("DELETE FROM events WHERE id = ANY(:ids)"), {"ids": event_ids})
    if created["companies"]:
        session.execute(
            text("DELETE FROM companies WHERE id = ANY(:ids)"), {"ids": created["companies"]}
        )
    session.commit()


def test_create_review_tasks_persists_real_rows(real_session: Session) -> None:
    company = Company(id=uuid.uuid4(), display_name="Review Test Co")
    real_session.add(company)
    real_session.commit()
    real_session.info["created"]["companies"].append(company.id)

    investigation = _investigation(final_status="NEEDS_REVIEW", failure_reason="budget_exceeded: x")
    investigation.company_id = company.id
    real_session.add(investigation)
    real_session.commit()
    real_session.info["created"]["investigations"].append(investigation.id)

    dossier = _dossier(investigation.id)
    real_session.add(dossier)
    real_session.commit()

    tasks = create_review_tasks(real_session, investigation, dossier, [])
    real_session.commit()
    assert len(tasks) == 1
    assert tasks[0].reason_code == BUDGET_EXCEEDED
    assert tasks[0].status == "open"


def test_list_open_tasks_orders_by_priority_then_created_at(real_session: Session) -> None:
    company = Company(id=uuid.uuid4(), display_name="List Open Tasks Co")
    real_session.add(company)
    real_session.commit()
    real_session.info["created"]["companies"].append(company.id)

    investigation = _investigation(final_status="NEEDS_REVIEW", failure_reason="budget_exceeded: x")
    investigation.company_id = company.id
    real_session.add(investigation)
    real_session.commit()
    real_session.info["created"]["investigations"].append(investigation.id)

    dossier = _dossier(investigation.id)
    real_session.add(dossier)
    real_session.commit()

    low = ReviewTask(dossier_id=dossier.id, reason_code=LOW_CONFIDENCE_EXTRACTION, priority=0)
    high = ReviewTask(dossier_id=dossier.id, reason_code=HIGH_SEVERITY_FINDING, priority=10)
    closed = ReviewTask(
        dossier_id=dossier.id, reason_code=BUDGET_EXCEEDED, priority=10, status="closed"
    )
    real_session.add_all([low, high, closed])
    real_session.commit()

    tasks = list_open_tasks(real_session)
    task_ids = [t.id for t in tasks]
    assert closed.id not in task_ids
    assert task_ids.index(high.id) < task_ids.index(low.id)


def test_list_open_tasks_respects_limit(real_session: Session) -> None:
    company = Company(id=uuid.uuid4(), display_name="List Open Tasks Limit Co")
    real_session.add(company)
    real_session.commit()
    real_session.info["created"]["companies"].append(company.id)

    investigation = _investigation(final_status="FINALISED")
    investigation.company_id = company.id
    real_session.add(investigation)
    real_session.commit()
    real_session.info["created"]["investigations"].append(investigation.id)

    dossier = _dossier(investigation.id)
    real_session.add(dossier)
    real_session.commit()

    real_session.add_all(
        [
            ReviewTask(dossier_id=dossier.id, reason_code=HIGH_SEVERITY_FINDING, priority=10),
            ReviewTask(dossier_id=dossier.id, reason_code=LOW_CONFIDENCE_EXTRACTION, priority=0),
        ]
    )
    real_session.commit()

    assert len(list_open_tasks(real_session, limit=1)) == 1


def test_get_task_dossier_returns_the_real_dossier(real_session: Session) -> None:
    company = Company(id=uuid.uuid4(), display_name="Get Task Dossier Co")
    real_session.add(company)
    real_session.commit()
    real_session.info["created"]["companies"].append(company.id)

    investigation = _investigation(final_status="FINALISED")
    investigation.company_id = company.id
    real_session.add(investigation)
    real_session.commit()
    real_session.info["created"]["investigations"].append(investigation.id)

    dossier = _dossier(investigation.id)
    real_session.add(dossier)
    real_session.commit()

    task = ReviewTask(dossier_id=dossier.id, reason_code=HIGH_SEVERITY_FINDING, priority=10)
    real_session.add(task)
    real_session.commit()

    found = get_task_dossier(real_session, task.id)
    assert found is not None
    assert found.id == dossier.id


def test_get_task_dossier_returns_none_for_a_claim_only_task(real_session: Session) -> None:
    company = Company(id=uuid.uuid4(), display_name="Claim Only Task Co")
    real_session.add(company)
    real_session.commit()
    real_session.info["created"]["companies"].append(company.id)

    investigation = _investigation(final_status="FINALISED")
    investigation.company_id = company.id
    real_session.add(investigation)
    real_session.commit()
    real_session.info["created"]["investigations"].append(investigation.id)

    claim = _event_claim(severity="low", tier="VERIFIED")
    claim.investigation_id = investigation.id
    real_session.add(claim)
    real_session.commit()

    task = ReviewTask(claim_id=claim.id, reason_code=LOW_CONFIDENCE_EXTRACTION, priority=0)
    real_session.add(task)
    real_session.commit()

    assert get_task_dossier(real_session, task.id) is None


def test_record_decision_appends_to_the_audit(real_session: Session) -> None:
    company = Company(id=uuid.uuid4(), display_name="Decision Test Co")
    real_session.add(company)
    real_session.commit()
    real_session.info["created"]["companies"].append(company.id)

    investigation = _investigation(final_status="FINALISED")
    investigation.company_id = company.id
    real_session.add(investigation)
    real_session.commit()
    real_session.info["created"]["investigations"].append(investigation.id)

    dossier = _dossier(investigation.id)
    real_session.add(dossier)
    real_session.commit()

    task = ReviewTask(dossier_id=dossier.id, reason_code=HIGH_SEVERITY_FINDING, priority=10)
    real_session.add(task)
    real_session.commit()

    updated = record_decision(real_session, task.id, "approve", "reviewer_a", notes="looks fine")
    assert updated.decision == "approve"
    assert updated.status == "closed"

    audit_rows = real_session.execute(
        text("SELECT actor, action FROM review_decisions_audit WHERE review_task_id = :id"),
        {"id": task.id},
    ).all()
    assert len(audit_rows) == 1
    assert audit_rows[0][0] == "reviewer_a"


def test_apply_event_feedback_creates_a_new_immutable_version_without_mutating_status(
    real_session: Session,
) -> None:
    event_type = real_session.scalar(select(EventType).where(EventType.code == "AUD_RESIGN"))
    assert event_type is not None
    event = Event(
        event_type_id=event_type.id,
        known_at=dt.datetime(2020, 1, 1, tzinfo=dt.UTC),
        severity="medium",
        status="candidate",
        detector_name="test",
        detector_version="1",
        confidence=0.5,
    )
    real_session.add(event)
    real_session.commit()
    real_session.info["created"]["events"].append(event.id)

    apply_event_feedback(real_session, event.id, "verified", "reviewer_b", notes="confirmed")

    real_session.refresh(event)
    assert event.status == "candidate"  # never mutated in place

    versions = real_session.scalars(
        select(EventVersion).where(EventVersion.event_id == event.id)
    ).all()
    assert len(versions) == 1
    assert versions[0].status == "verified"
    assert versions[0].reviewer == "reviewer_b"
