"""Tests for ledgerlight.agent.state_machine -- Phase 4 Sec4.

`run_investigation` commits internally (real steps must be durably
checkpointed for genuine crash-resume, not just flushed -- the same
lesson Phase 3 learned from scripts/process.py's single-transaction
risk). That makes the project's usual `db_session` fixture (which
wraps a test in one outer transaction, rolled back at teardown)
unusable here: an internal commit would commit that outer transaction
too. These tests instead use a real, independent session via the
production `make_session_factory`, and explicitly clean up every real
row they create afterward.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from ledgerlight.agent.budgets import BudgetConfig
from ledgerlight.agent.models import Claim, Dossier, Investigation, InvestigationStep
from ledgerlight.agent.state_machine import run_investigation
from ledgerlight.knowledge.models import Company

pytestmark = pytest.mark.integration


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

    created_company_ids: list[uuid.UUID] = []
    session.info["created_company_ids"] = created_company_ids
    try:
        yield session
    finally:
        _cleanup(session, created_company_ids)
        session.close()


def _cleanup(session: Session, company_ids: list[uuid.UUID]) -> None:
    if not company_ids:
        return
    session.execute(
        text(
            "DELETE FROM review_decisions_audit WHERE review_task_id IN "
            "(SELECT id FROM review_tasks WHERE dossier_id IN "
            "(SELECT id FROM dossiers WHERE investigation_id IN "
            "(SELECT id FROM investigations WHERE company_id = ANY(:ids))))"
        ),
        {"ids": company_ids},
    )
    session.execute(
        text(
            "DELETE FROM review_tasks WHERE dossier_id IN "
            "(SELECT id FROM dossiers WHERE investigation_id IN "
            "(SELECT id FROM investigations WHERE company_id = ANY(:ids)))"
        ),
        {"ids": company_ids},
    )
    session.execute(
        text(
            "DELETE FROM dossiers WHERE investigation_id IN "
            "(SELECT id FROM investigations WHERE company_id = ANY(:ids))"
        ),
        {"ids": company_ids},
    )
    session.execute(
        text(
            "DELETE FROM claims WHERE investigation_id IN "
            "(SELECT id FROM investigations WHERE company_id = ANY(:ids))"
        ),
        {"ids": company_ids},
    )
    session.execute(
        text(
            "DELETE FROM investigation_steps WHERE investigation_id IN "
            "(SELECT id FROM investigations WHERE company_id = ANY(:ids))"
        ),
        {"ids": company_ids},
    )
    session.execute(
        text("DELETE FROM investigations WHERE company_id = ANY(:ids)"), {"ids": company_ids}
    )
    session.execute(text("DELETE FROM companies WHERE id = ANY(:ids)"), {"ids": company_ids})
    session.commit()


def _make_company(session: Session, name: str) -> uuid.UUID:
    company = Company(id=uuid.uuid4(), display_name=name)
    session.add(company)
    session.commit()
    session.info["created_company_ids"].append(company.id)
    return company.id


def test_run_investigation_finalises_a_fresh_company_with_no_data(real_session: Session) -> None:
    """A fresh company with no real events/filings/ratings produces
    only the standing limitation claims + a 'no score' risk_signal --
    all of which should verify cleanly and reach FINALISED."""
    company_id = _make_company(real_session, "State Machine Fresh Co")
    outcome = run_investigation(
        real_session, company_id, dt.date(2020, 1, 1), "test", BudgetConfig()
    )
    assert outcome.investigation.final_status == "FINALISED"
    assert outcome.investigation.state == "FINALISE"
    assert outcome.rendered is not None
    assert "disclaimer" in outcome.rendered.sections


def test_run_investigation_needs_review_on_budget_exceeded(real_session: Session) -> None:
    company_id = _make_company(real_session, "State Machine Budget Co")
    outcome = run_investigation(
        real_session,
        company_id,
        dt.date(2020, 1, 1),
        "test",
        BudgetConfig(max_steps=1),
    )
    assert outcome.investigation.final_status == "NEEDS_REVIEW"
    assert outcome.investigation.failure_reason is not None
    assert "budget_exceeded" in outcome.investigation.failure_reason


def test_run_investigation_persists_a_dossier_even_on_needs_review(real_session: Session) -> None:
    company_id = _make_company(real_session, "State Machine Dossier Co")
    outcome = run_investigation(
        real_session, company_id, dt.date(2020, 1, 1), "test", BudgetConfig(max_steps=1)
    )
    dossier = real_session.query(Dossier).filter_by(investigation_id=outcome.investigation.id).one()
    assert dossier.status == "NEEDS_REVIEW"


def test_run_investigation_checkpoints_every_state(real_session: Session) -> None:
    company_id = _make_company(real_session, "State Machine Checkpoint Co")
    outcome = run_investigation(
        real_session, company_id, dt.date(2020, 1, 1), "test", BudgetConfig()
    )
    steps = (
        real_session.query(InvestigationStep)
        .filter_by(investigation_id=outcome.investigation.id)
        .order_by(InvestigationStep.step_no)
        .all()
    )
    states_seen = [s.state for s in steps]
    assert states_seen == ["PLAN", "GATHER", "TIMELINE", "DRAFT", "VERIFY"]
    assert steps[0].step_no == 0
    assert [s.step_no for s in steps] == list(range(len(steps)))


def test_run_investigation_resume_after_a_simulated_crash_gives_the_same_final_dossier(
    real_session: Session,
) -> None:
    """Simulates a real crash right after GATHER's checkpoint (the
    process is killed before TIMELINE ever runs): manually rewinds a
    completed investigation's state back to "TIMELINE" and deletes the
    claims/dossier that came after that point, then resumes. The
    final dossier must match a fresh, uninterrupted run on the same
    real company/as_of exactly."""
    as_of = dt.date(2020, 1, 1)
    company_id = _make_company(real_session, "State Machine Resume Co")
    first_pass = run_investigation(real_session, company_id, as_of, "test", BudgetConfig())
    assert first_pass.investigation.final_status == "FINALISED"
    first_pass_sections = first_pass.rendered.sections if first_pass.rendered else {}
    investigation_id = first_pass.investigation.id

    # Roll THAT SAME investigation back to a pre-DRAFT state to simulate
    # the crash, then resume it -- the real comparison is this one
    # investigation's own first-pass render against its resumed render,
    # never two different companies' dossiers (which would legitimately
    # differ by the real company name alone).

    real_session.query(Dossier).filter_by(investigation_id=investigation_id).delete()
    real_session.query(Claim).filter_by(investigation_id=investigation_id).delete()
    real_session.query(InvestigationStep).filter(
        InvestigationStep.investigation_id == investigation_id,
        InvestigationStep.state.in_(["TIMELINE", "DRAFT", "VERIFY", "REPAIR"]),
    ).delete(synchronize_session=False)
    investigation = real_session.get(Investigation, investigation_id)
    assert investigation is not None
    investigation.state = "TIMELINE"
    investigation.final_status = None
    investigation.failure_reason = None
    real_session.commit()

    resumed = run_investigation(
        real_session,
        company_id,
        as_of,
        "test",
        resume_investigation_id=investigation_id,
    )
    assert resumed.investigation.final_status == "FINALISED"
    assert resumed.rendered is not None
    assert resumed.rendered.sections == first_pass_sections
