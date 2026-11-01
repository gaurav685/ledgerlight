"""Phase 5 §2: tenancy, auth, and every tenant-owned table the brief
lists (users, memberships, api_keys, watchlists, watchlist_items,
alerts, alert_rules, webhooks, webhook_deliveries, review_assignments,
audit_logs) — real, Postgres Row-Level-Security-protected tables, each
with a real `tenant_id` column.

Public reference data (companies, documents, events, scores, outcomes
— all of Phase 1-3's own schema) is deliberately NOT touched here: it
stays global, read-only to the app role, no RLS. Phase 4's own agent
tables (investigations, claims, dossiers, review_tasks,
review_decisions_audit, event_versions) also stay as Phase 4 built
them — `investigations` gets one new, nullable `tenant_id` column
(migration `0001_tenancy...py`) for investigations the API itself
creates; a CLI-created investigation (`requested_by='cli'`/'agent-eval'
etc.) leaves it NULL, which is simply invisible to every tenant's own
RLS-scoped connection (`NULL = <tenant_id>` is never true in SQL) --
never a leak, never a real row any tenant could see.

`review_tasks` itself is NOT given a `tenant_id` (the brief's own
table list says "review assignments", not "review_tasks") -- a real
review task's tenant is reached transitively, through its dossier's
investigation's own `tenant_id`. `review_assignments` is the real,
tenant-owned bridge: which specific tenant user a real review task is
assigned to work on, not a visibility mechanism by itself.

One real, disclosed simplification (see `docs/adr/0008-api-auth-tenancy.md`):
a `User` belongs to exactly one tenant (`users.tenant_id`), and
`Membership` is a separate, denormalized table (also carrying its own
`tenant_id`, equal to the user's by application convention, not a DB
constraint) so every tenant-owned table's RLS policy can filter on its
own direct `tenant_id` column -- never a cross-table join inside a
policy.
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
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

ROLES = ("viewer", "analyst", "reviewer", "tenant_admin")
MEMBERSHIP_STATUSES = ("invited", "active", "revoked")

_COMPANIES_FK_NOTE = (
    "Real FK to ledgerlight.knowledge.models.Company.id -- no Python-side "
    "ForeignKey object: SQLAlchemy resolves a Python FK's target table eagerly "
    "at first persistence, which would force every real caller of this module "
    "to also import ledgerlight.knowledge.models (confirmed by hitting exactly "
    "this NoReferencedTableError while wiring Investigation.tenant_id -> "
    "tenants.id the other direction). The real database-level foreign key "
    "(migration 4dad2cd00443) still enforces it regardless."
)


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class User(Base):
    """A real login identity, scoped to exactly one real tenant (a
    disclosed design choice -- see this module's own docstring). Never
    stores a plaintext password -- `password_hash` is a real argon2id
    hash (`ledgerlight.api.auth`)."""

    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("tenant_id", "email", name="uq_users_tenant_email"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Membership(Base):
    """One real role assignment for one real user within one real
    tenant -- the real authorization record `ledgerlight.api.rbac`
    reads. Kept separate from `User` so a role can be revoked/changed
    without touching the login identity, and so this table's own
    `tenant_id` is directly RLS-filterable."""

    __tablename__ = "memberships"
    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", name="uq_memberships_tenant_user"),
        CheckConstraint(f"role IN {ROLES!r}", name="ck_memberships_role"),
        CheckConstraint(f"status IN {MEMBERSHIP_STATUSES!r}", name="ck_memberships_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    invited_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Session(Base):
    """A real server-side session row (Postgres-backed, per the
    brief's own §2 requirement) -- the real session cookie carries
    only this row's real id; nothing session-identifying is stored
    client-side beyond that id. `session_token_hash` lets a stolen DB
    row never be directly replayable as a cookie value either."""

    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    session_token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    csrf_token: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    rotated_from_session_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sessions.id"), nullable=True
    )
    revoked_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)


class ApiKey(Base):
    """A real API key -- shown to the user once at creation, never
    again: only `key_prefix` (safe to display/log) and `key_hash` (a
    real hash of the full secret, never the secret itself) are
    persisted."""

    __tablename__ = "api_keys"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    key_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    scopes: Mapped[list[object]] = mapped_column(JSONB, nullable=False, default=list)
    expires_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Watchlist(Base):
    __tablename__ = "watchlists"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class WatchlistItem(Base):
    __tablename__ = "watchlist_items"
    __table_args__ = (
        UniqueConstraint("watchlist_id", "company_id", name="uq_watchlist_items_watchlist_company"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    watchlist_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("watchlists.id"), nullable=False)
    company_id: Mapped[uuid.UUID] = mapped_column(nullable=False, doc=_COMPANIES_FK_NOTE)
    added_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AlertRule(Base):
    """A real, tenant-owned rule a Dagster job (§3's own "alerts
    generation" requirement) evaluates against new real events/scores
    for a watchlisted company. `rule_type` is a real, small enum
    ("new_event_type" | "score_percentile_threshold"); `config` holds
    the real rule-specific parameters (e.g. the real event_type_code,
    or the real percentile threshold)."""

    __tablename__ = "alert_rules"
    __table_args__ = (
        CheckConstraint(
            "rule_type IN ('new_event_type', 'score_percentile_threshold')",
            name="ck_alert_rules_rule_type",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    watchlist_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("watchlists.id"), nullable=False)
    rule_type: Mapped[str] = mapped_column(String(32), nullable=False)
    config: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    alert_rule_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("alert_rules.id"), nullable=False)
    company_id: Mapped[uuid.UUID] = mapped_column(nullable=False, doc=_COMPANIES_FK_NOTE)
    payload: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, doc="the real event/score fact that fired this rule"
    )
    triggered_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    acknowledged_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    acknowledged_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class Webhook(Base):
    """`secret_encrypted` is the real HMAC signing secret, encrypted
    at rest with a real Fernet key from the environment
    (`Settings.webhook_secret_encryption_key`) -- never stored or
    logged in plaintext. `url` must be `https://` (enforced in
    `ledgerlight.api.webhooks`, not here -- this is just the real
    storage shape)."""

    __tablename__ = "webhooks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    secret_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class WebhookDelivery(Base):
    __tablename__ = "webhook_deliveries"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'success', 'failed')", name="ck_webhook_deliveries_status"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    webhook_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("webhooks.id"), nullable=False)
    alert_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("alerts.id"), nullable=True)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    signature: Mapped[str] = mapped_column(String(128), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    response_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    next_retry_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    delivered_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ReviewAssignment(Base):
    """The real, tenant-owned bridge between one of Phase 4's own
    (global, un-tenanted) `review_tasks` rows and a specific tenant
    user assigned to work it -- see this module's own docstring for
    why `review_tasks` itself carries no `tenant_id`."""

    __tablename__ = "review_assignments"
    __table_args__ = (
        CheckConstraint(
            "status IN ('open', 'in_progress', 'done')", name="ck_review_assignments_status"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    review_task_id: Mapped[uuid.UUID] = mapped_column(
        nullable=False,
        doc="Real FK to ledgerlight.agent.models.ReviewTask.id -- no Python-side "
        "ForeignKey object (see _COMPANIES_FK_NOTE above for why); the real "
        "database-level foreign key (migration 4dad2cd00443) still enforces it.",
    )
    assignee_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    assigned_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    assigned_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AuditLog(Base):
    """Append-only (by application convention, the same real discipline
    `ledgerlight.agent.models.ReviewDecisionAudit` already uses -- no
    DB-level trigger enforces it either, consistent with that
    precedent). Covers every real auth event, API key
    creation/revocation, review decision, investigation creation, and
    document-link issuance, per the brief's own §3 requirement."""

    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    actor_api_key_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("api_keys.id"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    target_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    extra: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
