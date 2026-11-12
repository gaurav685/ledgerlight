"""Phase 4 §4: the explicit, checkpointed investigation state machine.

PLAN -> GATHER -> TIMELINE -> DRAFT -> VERIFY -> REPAIR -> FINALISE,
terminal outcomes FINALISED or NEEDS_REVIEW. A custom state machine,
not a heavy agent framework -- justified in `docs/adr/0007-investigation-agent.md`.

Design (see `docs/phase-4/progress.md` for the reasoning): claims are
persisted as real `Claim` rows progressively during TIMELINE/DRAFT, so
`render_offline` always works from real claim IDs. Exactly one real
`Dossier` row is persisted at the very end -- FINALISE or the terminal
NEEDS_REVIEW -- carrying the last real render, even on failure, so a
human reviewer always has something concrete to look at. REPAIR never
deletes a `Claim` row (this project never deletes real rows); it marks
failed claims `verification_status="failed"` and re-renders using only
the claims that still pass, which is what "remove failed claims" means
here -- never replaced with a new, different unsupported claim.

Resuming a crashed run re-invokes `run_investigation` with
`resume_investigation_id` set: it reads `Investigation.state` (the next
state to execute) and continues from there, re-deriving nothing that
was already persisted.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from ledgerlight.agent.budgets import BudgetConfig, BudgetExceeded, Usage, check_budgets
from ledgerlight.agent.claims import (
    ClaimDraft,
    claim_from_risk_score,
    claims_from_events,
    claims_from_outcomes_context,
    claims_from_timeline,
    entity_history_limitation_claim,
    standing_limitation_claims,
)
from ledgerlight.agent.models import Claim, Dossier, Investigation, InvestigationStep
from ledgerlight.agent.render import (
    RENDERER_NAME,
    RENDERER_VERSION,
    RenderedDossier,
    render_offline,
)
from ledgerlight.agent.review import create_review_tasks
from ledgerlight.agent.tools import (
    get_entity_history,
    get_events,
    get_outcomes_context,
    get_risk_score,
    get_timeline,
)
from ledgerlight.agent.verifier import (
    DossierVerificationResult,
    find_contradictions,
    verify_dossier,
)
from ledgerlight.knowledge.models import Company

STATE_ORDER = ["PLAN", "GATHER", "TIMELINE", "DRAFT", "VERIFY", "REPAIR", "FINALISE"]


@dataclass
class InvestigationOutcome:
    investigation: Investigation
    rendered: RenderedDossier | None


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def _next_step_no(session: Session, investigation_id: uuid.UUID) -> int:
    existing = session.scalars(
        select(InvestigationStep.step_no).where(
            InvestigationStep.investigation_id == investigation_id
        )
    ).all()
    return (max(existing) + 1) if existing else 0


def _checkpoint(
    session: Session,
    investigation: Investigation,
    state: str,
    tool_calls: list[object],
    outputs: dict[str, object],
) -> None:
    step_no = _next_step_no(session, investigation.id)
    session.add(
        InvestigationStep(
            investigation_id=investigation.id,
            step_no=step_no,
            state=state,
            tool_calls=tool_calls,
            outputs=outputs,
            finished_at=_now(),
        )
    )
    session.flush()


def _check_budgets_now(usage: Usage, budget: BudgetConfig, wall_start: dt.datetime) -> None:
    usage.wall_seconds = (_now() - wall_start).total_seconds()
    check_budgets(usage, budget)


def _persist_claims(
    session: Session, investigation_id: uuid.UUID, drafts: list[ClaimDraft]
) -> list[Claim]:
    persisted: list[Claim] = []
    for draft in drafts:
        claim = Claim(
            investigation_id=investigation_id,
            claim_type=draft.claim_type,
            payload=draft.payload,
            evidence=draft.evidence_json(),
        )
        session.add(claim)
        persisted.append(claim)
    session.flush()
    return persisted


def _render(
    session: Session, claims: list[Claim], company_name: str, as_of_iso: str
) -> RenderedDossier:
    """`render_offline` with real, freshly-computed contradictions
    always passed in -- `find_contradictions` is a pure function of
    the active claim set, so every render (DRAFT, REPAIR, and VERIFY's
    own resume fallback) must recompute and include it. Without this,
    a real contradiction `verify_dossier` detects would be returned in
    its own result and then silently dropped, never reaching the
    persisted dossier's "Conflicting evidence" section -- a real gap
    found while writing Sec9's contradictory-sources adversarial test."""
    return render_offline(
        session, claims, company_name, as_of_iso, contradictions=find_contradictions(claims)
    )


def run_investigation(
    session: Session,
    company_id: uuid.UUID,
    as_of: dt.date,
    requested_by: str,
    budget_config: BudgetConfig | None = None,
    resume_investigation_id: uuid.UUID | None = None,
    tenant_id: uuid.UUID | None = None,
) -> InvestigationOutcome:
    """`tenant_id` is Phase 5 §3's own addition: set only when the real
    API itself creates this investigation on behalf of a real tenant
    -- every CLI/agent-eval call site leaves it `None` (unchanged
    behaviour), which is exactly what `investigations.tenant_id`'s own
    real RLS policy expects (a NULL tenant_id is never visible to any
    tenant's own scoped connection -- see that column's own doc). A
    real API-created investigation left with a NULL tenant_id here
    would become permanently invisible to the very tenant who asked
    for it, so the real app-role caller (`ledgerlight.api.routers.dossiers`)
    always passes its own real tenant_id through."""
    if resume_investigation_id is not None:
        investigation = session.get(Investigation, resume_investigation_id)
        assert investigation is not None, "resume_investigation_id does not exist"
        # A real, previously-undiscovered bug (found in Phase 6A §8's own
        # failure-recovery drill): resuming always re-derived the real
        # PERSISTED budget, silently ignoring any `budget_config` the
        # caller passed -- so an operator resuming a budget-exhausted
        # investigation with a larger budget (exactly what
        # `scripts/investigate.py --resume ... --max-steps N` is for)
        # had the new budget discarded and immediately hit the same old
        # exhausted one again. An explicit override now wins, and is
        # persisted so a later resume sees it too.
        budget = budget_config or BudgetConfig.from_json(investigation.budget_config)
        investigation.budget_config = budget.to_json()
        usage = Usage.from_json(investigation.usage)
        # A second real bug found alongside the first: `final_status`/
        # `failure_reason` from the PRIOR attempt were never cleared, so
        # the `if investigation.final_status is None` gate below (which
        # decides FINALISED vs NEEDS_REVIEW) was always already false on
        # a resume -- a resumed run that genuinely reached FINALISE this
        # time would still be permanently mislabelled NEEDS_REVIEW with a
        # stale failure_reason from the earlier, unrelated failure.
        investigation.final_status = None
        investigation.failure_reason = None
    else:
        budget = budget_config or BudgetConfig()
        usage = Usage()
        investigation = Investigation(
            id=uuid.uuid4(),
            company_id=company_id,
            as_of=as_of,
            requested_by=requested_by,
            tenant_id=tenant_id,
            state="PLAN",
            budget_config=budget.to_json(),
            usage=usage.to_json(),
        )
        session.add(investigation)
        session.commit()

    wall_start = investigation.started_at or _now()
    rendered: RenderedDossier | None = None

    try:
        if investigation.state == "PLAN":
            usage.steps += 1
            _check_budgets_now(usage, budget, wall_start)
            plan = [
                "get_events",
                "get_timeline",
                "get_risk_score",
                "get_outcomes_context",
                "get_entity_history",
            ]
            _checkpoint(session, investigation, "PLAN", [], {"plan": plan})
            investigation.state = "GATHER"
            investigation.usage = usage.to_json()
            session.commit()

        gathered: dict[str, object] = {}
        if investigation.state == "GATHER":
            usage.steps += 1
            _check_budgets_now(usage, budget, wall_start)
            events_env = get_events(session, company_id, as_of)
            usage.tool_calls += 1
            timeline_env = get_timeline(session, company_id, as_of)
            usage.tool_calls += 1
            risk_env = get_risk_score(session, company_id, as_of)
            usage.tool_calls += 1
            outcomes_env = get_outcomes_context(session, company_id, as_of)
            usage.tool_calls += 1
            entity_env = get_entity_history(session, company_id, as_of)
            usage.tool_calls += 1
            _check_budgets_now(usage, budget, wall_start)

            gathered = {
                "events": events_env,
                "timeline": timeline_env,
                "risk": risk_env,
                "outcomes": outcomes_env,
                "entity": entity_env,
            }
            _checkpoint(
                session,
                investigation,
                "GATHER",
                [{"tool": name} for name in gathered],
                {"tool_calls": usage.tool_calls},
            )
            investigation.state = "TIMELINE"
            investigation.usage = usage.to_json()
            session.commit()
        else:
            gathered = {
                "events": get_events(session, company_id, as_of),
                "timeline": get_timeline(session, company_id, as_of),
                "risk": get_risk_score(session, company_id, as_of),
                "outcomes": get_outcomes_context(session, company_id, as_of),
                "entity": get_entity_history(session, company_id, as_of),
            }

        if investigation.state == "TIMELINE":
            usage.steps += 1
            _check_budgets_now(usage, budget, wall_start)
            timeline_drafts = claims_from_timeline(gathered["timeline"].data)  # type: ignore[attr-defined]
            persisted = _persist_claims(session, investigation.id, timeline_drafts)
            _checkpoint(
                session,
                investigation,
                "TIMELINE",
                [],
                {"claim_ids": [str(c.id) for c in persisted]},
            )
            investigation.state = "DRAFT"
            investigation.usage = usage.to_json()
            session.commit()

        if investigation.state == "DRAFT":
            usage.steps += 1
            _check_budgets_now(usage, budget, wall_start)
            drafts: list[ClaimDraft] = []
            drafts.extend(claims_from_events(gathered["events"].data))  # type: ignore[attr-defined]
            drafts.extend(claims_from_outcomes_context(gathered["outcomes"].data))  # type: ignore[attr-defined]
            drafts.append(claim_from_risk_score(gathered["risk"].data))  # type: ignore[attr-defined]
            drafts.extend(standing_limitation_claims())
            entity_limitation = entity_history_limitation_claim(gathered["entity"].data)  # type: ignore[attr-defined]
            if entity_limitation is not None:
                drafts.append(entity_limitation)
            _persist_claims(session, investigation.id, drafts)

            company = session.get(Company, company_id)
            company_name = company.display_name if company is not None else str(company_id)
            active_claims = _active_claims(session, investigation.id)
            rendered = _render(session, active_claims, company_name, as_of.isoformat())

            _checkpoint(
                session,
                investigation,
                "DRAFT",
                [],
                {"claim_count": len(active_claims)},
            )
            investigation.state = "VERIFY"
            investigation.usage = usage.to_json()
            session.commit()

        repair_round = 0
        while investigation.state in ("VERIFY", "REPAIR"):
            if investigation.state == "VERIFY":
                usage.steps += 1
                _check_budgets_now(usage, budget, wall_start)
                active_claims = _active_claims(session, investigation.id)
                if rendered is None:
                    company = session.get(Company, company_id)
                    company_name = company.display_name if company is not None else str(company_id)
                    rendered = _render(session, active_claims, company_name, as_of.isoformat())
                try:
                    result = verify_dossier(session, active_claims, rendered, as_of)
                except Exception as verify_exc:
                    # Sec9's explicit requirement: a verifier crash or timeout fails
                    # closed to NEEDS_REVIEW, never propagates uncaught and never
                    # silently passes. Whatever real claims/dossier already exist
                    # (this step's own render, already in `rendered`) are kept, not
                    # discarded -- a human reviewer still has something concrete.
                    investigation.final_status = "NEEDS_REVIEW"
                    investigation.failure_reason = (
                        f"verifier_crashed: {type(verify_exc).__name__}: {verify_exc}"
                    )
                    investigation.usage = usage.to_json()
                    _checkpoint(
                        session,
                        investigation,
                        "VERIFY",
                        [],
                        {"verifier_crashed": True, "error": str(verify_exc)},
                    )
                    session.commit()
                    break
                _record_verification(active_claims, result, rendered)
                _checkpoint(
                    session,
                    investigation,
                    "VERIFY",
                    [],
                    {
                        "passed": result.passed,
                        "failed_claim_ids": [str(c) for c in result.failed_claim_ids],
                        "count_mismatches": result.count_mismatches,
                    },
                )
                investigation.usage = usage.to_json()

                if result.passed:
                    investigation.state = "FINALISE"
                    session.commit()
                    break
                if repair_round >= budget.max_repair_rounds:
                    investigation.final_status = "NEEDS_REVIEW"
                    investigation.failure_reason = (
                        f"verification_failed after {repair_round} repair round(s): "
                        f"{len(result.failed_claim_ids)} claim(s) failing, "
                        f"{len(result.sentence_mapping_failures)} sentence-mapping failure(s), "
                        f"{len(result.banned_language_failures)} banned-language failure(s), "
                        f"{len(result.sentence_value_failures)} sentence-value failure(s), "
                        f"{len(result.count_mismatches)} count-mismatch failure(s)"
                    )
                    session.commit()
                    break
                investigation.state = "REPAIR"
                session.commit()

            if investigation.state == "REPAIR":
                usage.steps += 1
                _check_budgets_now(usage, budget, wall_start)
                active_claims = _active_claims(session, investigation.id)
                company = session.get(Company, company_id)
                company_name = company.display_name if company is not None else str(company_id)
                rendered = _render(session, active_claims, company_name, as_of.isoformat())
                _checkpoint(
                    session, investigation, "REPAIR", [], {"repair_round": repair_round + 1}
                )
                repair_round += 1
                investigation.state = "VERIFY"
                investigation.usage = usage.to_json()
                session.commit()

        if investigation.final_status is None:
            if investigation.state == "FINALISE":
                usage.steps += 1
                _check_budgets_now(usage, budget, wall_start)
                investigation.final_status = "FINALISED"
            else:
                investigation.final_status = "NEEDS_REVIEW"
                if investigation.failure_reason is None:
                    investigation.failure_reason = f"stopped in state {investigation.state}"

        dossier = _persist_dossier(session, investigation, rendered)
        create_review_tasks(
            session,
            investigation,
            dossier,
            _active_claims(session, investigation.id),
            _failed_claims(session, investigation.id),
        )

    except BudgetExceeded as exc:
        investigation.final_status = "NEEDS_REVIEW"
        investigation.failure_reason = exc.reason
        investigation.usage = usage.to_json()
        dossier = _persist_dossier(session, investigation, rendered)
        create_review_tasks(
            session,
            investigation,
            dossier,
            _active_claims(session, investigation.id),
            _failed_claims(session, investigation.id),
        )

    investigation.finished_at = _now()
    session.commit()
    return InvestigationOutcome(investigation=investigation, rendered=rendered)


def _active_claims(session: Session, investigation_id: uuid.UUID) -> list[Claim]:
    return list(
        session.scalars(
            select(Claim)
            .where(Claim.investigation_id == investigation_id)
            .where(Claim.verification_status != "failed")
            .order_by(Claim.created_at)
        ).all()
    )


def _failed_claims(session: Session, investigation_id: uuid.UUID) -> list[Claim]:
    """Phase 6 Correction 2 Sec2: the real claims REPAIR removed from
    this investigation -- fed to create_review_tasks so routing can
    catch a high-severity finding or a whole section REPAIR silently
    dropped, which _active_claims's own exclusion otherwise hides."""
    return list(
        session.scalars(
            select(Claim)
            .where(Claim.investigation_id == investigation_id)
            .where(Claim.verification_status == "failed")
            .order_by(Claim.created_at)
        ).all()
    )


def _record_verification(
    claims: list[Claim], result: DossierVerificationResult, rendered: RenderedDossier
) -> None:
    results_by_id = {r.claim_id: r for r in result.claim_results}
    claims_by_id = {c.id: c for c in claims}

    for claim in claims:
        claim_result = results_by_id.get(claim.id)
        if claim_result is None:
            continue
        claim.verification_status = "passed" if claim_result.passed else "failed"
        claim.verification_checks = [
            {"check_name": c.check_name, "passed": c.passed, "detail": c.detail}
            for c in claim_result.checks
        ]

    # Sentence-level failures (banned language, a sentence number not found
    # in its own mapped claims) are not per-claim verify_claim results --
    # resolve the failing sentence key back to its real claim ID(s) via
    # claim_id_map and mark those claims failed too, so REPAIR actually
    # removes them on re-render (a "no claim ID mapped" sentence_mapping
    # failure has no real claim to blame; it is a renderer defect, not
    # something REPAIR can fix by removing a claim).
    for failure in [*result.banned_language_failures, *result.sentence_value_failures]:
        key = failure.split(":", 2)
        sentence_key = f"{key[0]}:{key[1]}" if len(key) >= 2 else failure
        for claim_id_str in rendered.claim_id_map.get(sentence_key, []):
            referenced_claim = claims_by_id.get(uuid.UUID(claim_id_str))
            if referenced_claim is not None:
                referenced_claim.verification_status = "failed"


def _persist_dossier(
    session: Session, investigation: Investigation, rendered: RenderedDossier | None
) -> Dossier:
    existing_versions = session.scalars(
        select(Dossier.version).where(Dossier.investigation_id == investigation.id)
    ).all()
    version = (max(existing_versions) + 1) if existing_versions else 1

    dossier = Dossier(
        investigation_id=investigation.id,
        version=version,
        status=investigation.final_status or "NEEDS_REVIEW",
        sections=rendered.sections if rendered else {},
        claim_id_map=rendered.claim_id_map if rendered else {},
        renderer_name=RENDERER_NAME,
        renderer_version=RENDERER_VERSION,
    )
    session.add(dossier)
    session.flush()
    return dossier
