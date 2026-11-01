"""Phase 4 §2 data model: the investigation agent's own tables.

Shares `Base` with `ledgerlight.db.models` and `ledgerlight.knowledge.models`
so all three live in one Alembic migration history against the same
application database (never a second database -- see ADR 0004, carried
over from Phase 2/3). Evidence links use the same (document_version_id,
page_number, char_start, char_end) shape as
`ledgerlight.knowledge.models.EventField`'s evidence columns, since
`DocumentPage.raw_text` is the one real, immutable source of truth every
citation resolves against (its own docstring already anticipates this:
"Phase 4 citations reference character offsets into it").

`investigations`/`investigation_steps`/`claims`/`dossiers` are the agent's
own write surface (the brief's narrow repository layer); `review_tasks`/
`review_decisions_audit` are the human review workflow's.
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ledgerlight.db.models import Base


class Investigation(Base):
    """One real investigation run for one (company, as_of) point-in-time
    anchor -- the state machine's own row, checkpointed via
    `InvestigationStep`. `state` is the current state
    (PLAN/GATHER/TIMELINE/DRAFT/VERIFY/REPAIR/FINALISE); `final_status` is
    set only once a terminal outcome (FINALISED or NEEDS_REVIEW) is
    reached."""

    __tablename__ = "investigations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"), nullable=False)
    as_of: Mapped[dt.date] = mapped_column(Date, nullable=False)
    requested_by: Mapped[str] = mapped_column(String(64), nullable=False)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        nullable=True,
        doc="Phase 5 §2: set only for an investigation the API itself created on "
        "behalf of a real tenant. NULL for a CLI-created investigation -- never "
        "visible to any tenant's own RLS-scoped connection as a result. No "
        "Python-side ForeignKey object here deliberately -- `ledgerlight.api.models`"
        " (which owns the real `tenants` table) is not imported by every Phase "
        "1-4 entry point, and SQLAlchemy resolves a Python FK's target table "
        "eagerly at first persistence, which would break them. The real "
        "database-level foreign key (migration `4dad2cd00443`) still enforces "
        "this regardless of what the ORM model declares.",
    )

    state: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="PLAN",
        doc="PLAN | GATHER | TIMELINE | DRAFT | VERIFY | REPAIR | FINALISE",
    )
    final_status: Mapped[str | None] = mapped_column(
        String(16), nullable=True, doc="FINALISED | NEEDS_REVIEW"
    )
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    budget_config: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        doc="max_steps, max_wall_seconds, max_tool_calls, max_llm_tokens, max_cost_usd",
    )
    usage: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        doc="real, running totals: steps, wall_seconds, tool_calls, llm_tokens, cost_usd",
    )

    started_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class InvestigationStep(Base):
    """One checkpointed step of one investigation -- a crashed run resumes
    from `max(step_no)` for its `investigation_id`, never re-running an
    already-committed step. `tool_calls` records every real tool
    invocation (name, arguments, a reference to its stored result) made
    during this step; `outputs` is this step's own real produced state
    (e.g. the claims it built), never fabricated placeholder content."""

    __tablename__ = "investigation_steps"
    __table_args__ = (
        UniqueConstraint("investigation_id", "step_no", name="uq_investigation_steps_inv_step"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    investigation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("investigations.id"), nullable=False
    )
    step_no: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)

    tool_calls: Mapped[list[object]] = mapped_column(JSONB, nullable=False, default=list)
    outputs: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)

    started_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Claim(Base):
    """The source of truth for every piece of real dossier content --
    §2. `payload` is the real structured content (entity IDs, dates,
    numbers with units, event_type, tier); `evidence` is a real, non-empty
    list of `{document_version_id, page_number, char_start, char_end}`
    spans into real, immutable `document_pages.raw_text`.
    `verification_checks` records every real check the verifier ran
    against this claim, by name, with its own pass/fail and detail --
    never a single collapsed boolean."""

    __tablename__ = "claims"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    investigation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("investigations.id"), nullable=False
    )
    claim_type: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        doc="event | timeline_entry | metric | risk_signal | limitation",
    )
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    evidence: Mapped[list[object]] = mapped_column(JSONB, nullable=False)

    verification_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending", doc="pending | passed | failed | repaired"
    )
    verification_checks: Mapped[list[object]] = mapped_column(JSONB, nullable=False, default=list)

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Dossier(Base):
    """One real, immutable rendered dossier version for an investigation
    -- §6. A revision (e.g. after REPAIR, or a later re-render) creates a
    NEW row with `version` incremented, never an edit in place.
    `claim_id_map` maps every rendered sentence to the real claim IDs it
    is built from, so "every sentence maps to at least one claim ID" (§5)
    is directly checkable against this column, not re-derived."""

    __tablename__ = "dossiers"
    __table_args__ = (
        UniqueConstraint("investigation_id", "version", name="uq_dossiers_investigation_version"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    investigation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("investigations.id"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(16), nullable=False, doc="FINALISED | NEEDS_REVIEW")

    sections: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        doc="the 8 real rendered sections -- summary, chronology, findings, "
        "risk_signals, conflicting_evidence, limitations, sources, disclaimer",
    )
    claim_id_map: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, doc="sentence index -> real claim id list"
    )

    renderer_name: Mapped[str] = mapped_column(
        String(64), nullable=False, doc="offline_template | the real LLM model name"
    )
    renderer_version: Mapped[str] = mapped_column(String(32), nullable=False)
    prompt_version: Mapped[str | None] = mapped_column(String(32), nullable=True)

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ReviewTask(Base):
    """One real human-review task -- §7. References either a dossier or a
    single claim (never neither); `seeded_qc` marks a deliberately-flawed
    item injected by `qc-seed`, with `expected_outcome` recording what a
    correct reviewer decision should be -- seeded items are excluded from
    all real statistics (§7's own explicit rule)."""

    __tablename__ = "review_tasks"
    __table_args__ = (
        CheckConstraint(
            "dossier_id IS NOT NULL OR claim_id IS NOT NULL",
            name="ck_review_tasks_has_a_real_reference",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    dossier_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("dossiers.id"), nullable=True)
    claim_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("claims.id"), nullable=True)

    reason_code: Mapped[str] = mapped_column(String(32), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="open", doc="open | in_review | closed"
    )
    assignee: Mapped[str | None] = mapped_column(String(64), nullable=True)

    decision: Mapped[str | None] = mapped_column(
        String(32), nullable=True, doc="approve | approve_with_edits | reject | escalate"
    )
    decision_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    seeded_qc: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    expected_outcome: Mapped[str | None] = mapped_column(String(32), nullable=True)

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ReviewDecisionAudit(Base):
    """Append-only audit trail for every real action taken on a
    `ReviewTask` -- §7. Never updated or deleted; a correction is a new
    row, same as every other append-only audit table in this project
    (`IdentifierWindowCorrection`, from Phase 3)."""

    __tablename__ = "review_decisions_audit"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    review_task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("review_tasks.id"), nullable=False)
    actor: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    before: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    after: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class EventVersion(Base):
    """Phase 4 §7 feedback loop: a reviewer decision on a claim built from
    an `Event` can mark that event VERIFIED or rejected by creating a NEW
    version here -- `events.status` itself is never mutated in place, so
    the full real history of what a human decided, and when, is always
    reconstructable. This updates real reliability statistics
    (`docs/modelling/event-reliability.md`'s own numbers, on a future
    refresh) but never touches the frozen Phase 1/2 test split -- no
    column here references `label_items` or any gold-label table."""

    __tablename__ = "event_versions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("events.id"), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, doc="candidate | verified | rejected | needs_review"
    )
    reviewer: Mapped[str] = mapped_column(String(64), nullable=False)
    review_task_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("review_tasks.id"), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
