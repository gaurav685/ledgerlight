"""Phase 5 §3: Pydantic request/response models for the real `/v1` API.
Kept separate from `ledgerlight.api.models` (the real ORM layer) on
purpose -- a schema here is the real wire contract, not a 1:1 mirror of
a table; several (e.g. `IdentityOut`) deliberately omit real columns
(password hashes, token hashes) that must never leave the server.
"""

from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    """The one real error shape every failed `/v1` response uses --
    never a raw stack trace, never an framework-default error body."""

    error: str
    detail: str
    request_id: str | None = None


# --- auth -----------------------------------------------------------------


class LoginRequest(BaseModel):
    tenant_slug: str
    email: str
    password: str


class IdentityOut(BaseModel):
    user_id: uuid.UUID | None
    tenant_id: uuid.UUID
    role: str
    api_key_id: uuid.UUID | None = None


class LoginResponse(BaseModel):
    identity: IdentityOut
    csrf_token: str


# --- api keys ---------------------------------------------------------------


class ApiKeyCreateRequest(BaseModel):
    name: str
    scopes: list[str] = Field(default_factory=list)
    expires_at: dt.datetime | None = None


class ApiKeyCreateResponse(BaseModel):
    """`raw_key` is returned exactly once, on creation, and never again --
    the real server only ever persists its hash."""

    id: uuid.UUID
    name: str
    key_prefix: str
    scopes: list[str]
    expires_at: dt.datetime | None
    raw_key: str


class ApiKeyOut(BaseModel):
    id: uuid.UUID
    name: str
    key_prefix: str
    scopes: list[str]
    expires_at: dt.datetime | None
    revoked_at: dt.datetime | None
    last_used_at: dt.datetime | None
    created_at: dt.datetime


# --- watchlists ---------------------------------------------------------------


class WatchlistCreateRequest(BaseModel):
    name: str


class WatchlistOut(BaseModel):
    id: uuid.UUID
    name: str
    created_at: dt.datetime


class WatchlistItemCreateRequest(BaseModel):
    company_id: uuid.UUID


class WatchlistItemOut(BaseModel):
    id: uuid.UUID
    watchlist_id: uuid.UUID
    company_id: uuid.UUID
    added_at: dt.datetime


# --- alert rules / alerts ----------------------------------------------------


class AlertRuleCreateRequest(BaseModel):
    watchlist_id: uuid.UUID
    rule_type: str
    config: dict[str, object]


class AlertRuleOut(BaseModel):
    id: uuid.UUID
    watchlist_id: uuid.UUID
    rule_type: str
    config: dict[str, object]
    is_active: bool
    created_at: dt.datetime


class AlertOut(BaseModel):
    id: uuid.UUID
    alert_rule_id: uuid.UUID
    company_id: uuid.UUID
    payload: dict[str, object]
    triggered_at: dt.datetime
    acknowledged_at: dt.datetime | None


# --- webhooks -----------------------------------------------------------------


class WebhookCreateRequest(BaseModel):
    url: str


class WebhookCreateResponse(BaseModel):
    """`raw_secret` is returned exactly once, on creation -- the real
    server only ever persists it Fernet-encrypted."""

    id: uuid.UUID
    url: str
    is_active: bool
    raw_secret: str


class WebhookOut(BaseModel):
    id: uuid.UUID
    url: str
    is_active: bool
    created_at: dt.datetime


class WebhookDeliveryOut(BaseModel):
    id: uuid.UUID
    webhook_id: uuid.UUID
    status: str
    attempt_count: int
    response_code: int | None
    created_at: dt.datetime
    delivered_at: dt.datetime | None


class WebhookTestRequest(BaseModel):
    pass


# --- companies / events / scores ----------------------------------------------


class CompanyOut(BaseModel):
    id: uuid.UUID
    name: str
    cin: str | None = None
    nse_symbol: str | None = None
    bse_code: str | None = None


class EventOut(BaseModel):
    id: uuid.UUID
    company_id: uuid.UUID
    event_type_code: str
    status: str
    event_time: dt.date | None
    known_at: dt.date | None
    summary: str | None


class ScoreOut(BaseModel):
    company_id: uuid.UUID
    as_of: dt.date
    score: float
    model_version: str
    shap_values: dict[str, float] | None = None
    model_limitations: str


class CredibilityOut(BaseModel):
    company_id: uuid.UUID
    as_of: dt.date
    available: bool
    reason: str | None = None
    value: float | None = None


# --- dossiers / review ---------------------------------------------------------


class InvestigationCreateRequest(BaseModel):
    company_id: uuid.UUID
    as_of: dt.date


class InvestigationOut(BaseModel):
    id: uuid.UUID
    company_id: uuid.UUID
    as_of: dt.date
    state: str
    final_status: str | None
    started_at: dt.datetime
    finished_at: dt.datetime | None


class DossierOut(BaseModel):
    id: uuid.UUID
    investigation_id: uuid.UUID
    version: int
    status: str
    sections: dict[str, object]
    claim_id_map: dict[str, object]
    created_at: dt.datetime


class ReviewTaskOut(BaseModel):
    id: uuid.UUID
    dossier_id: uuid.UUID | None
    claim_id: uuid.UUID | None
    reason_code: str
    priority: int
    status: str
    assignee: str | None
    decision: str | None
    created_at: dt.datetime


class ReviewDecisionRequest(BaseModel):
    decision: str
    notes: str | None = None


# --- admin: users / roles / audit log --------------------------------------------


class UserCreateRequest(BaseModel):
    email: str
    password: str
    role: str


class UserOut(BaseModel):
    user_id: uuid.UUID
    email: str
    role: str
    membership_status: str
    is_active: bool
    created_at: dt.datetime


class RoleUpdateRequest(BaseModel):
    role: str


class AuditLogOut(BaseModel):
    id: uuid.UUID
    actor_user_id: uuid.UUID | None
    actor_api_key_id: uuid.UUID | None
    action: str
    target_type: str | None
    target_id: str | None
    created_at: dt.datetime


# --- documents ------------------------------------------------------------------


class SignedDocumentLinkOut(BaseModel):
    url: str
    expires_in_seconds: int


class DocumentPageTextOut(BaseModel):
    """The real, immutable extracted text for one page -- the one real
    source of truth every citation's `char_start`/`char_end` resolves
    against (`ledgerlight.db.models.DocumentPage`'s own docstring).
    The frontend's evidence viewer highlights the cited span directly
    against this text, never against a rendered PDF's own coordinates."""

    page_number: int
    raw_text: str
    char_count: int
