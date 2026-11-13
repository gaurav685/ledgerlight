"""Enhancement 1: Governance Event Study schema.

Two real tables: `event_study_runs` (one row per real run -- the
frozen spec it ran under, a hash of the real input data it actually
used, the git SHA, and the full aggregate metrics table) and
`event_study_event_results` (one row per real individual event this
run actually scored -- its own real abnormal returns per window,
placebo comparison, and a real evidence trace back to the source
CARE/SEBI/IBBI row this event came from).

See `docs/enhancements/event-study/spec.md` for the real methodology
these columns implement -- never changed independently of that spec.
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

import ledgerlight.knowledge.models  # noqa: F401 -- registers `companies` on Base.metadata,

# a real dependency of EventStudyEventResult.company_id's ForeignKey below: without this,
# any process that imports only this module (never ledgerlight.knowledge.models directly)
# fails at flush time with NoReferencedTableError, found running the real first study.
from ledgerlight.db.models import Base


class EventStudyRun(Base):
    """One real run of the governance event study. `spec_sha256` must
    match a real, already-frozen `model_registry` row
    (`model_name="event-study-spec"`) -- enforced by
    `ledgerlight.research.event_study.run_event_study`, never by a DB
    constraint alone, since `model_registry` is a separate table."""

    __tablename__ = "event_study_runs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    spec_version: Mapped[str] = mapped_column(String(32), nullable=False)
    spec_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    data_snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    git_sha: Mapped[str] = mapped_column(String(40), nullable=False)
    requested_by: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="completed")
    event_counts_json: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    metrics_json: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class EventStudyEventResult(Base):
    """One real individual event scored by one real run. `car_by_window`
    and `window_n_by_window` are keyed by the real window names in
    `spec.v1.json`'s own `event_windows` list (e.g. `"CAR_m1_p1"`) --
    a window missing from either dict means that specific event had no
    real, available data for that specific window (spec §7's own
    per-window-N rule), never a silently-assumed zero."""

    __tablename__ = "event_study_event_results"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("event_study_runs.id"), nullable=False)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"), nullable=False)
    event_type_code: Mapped[str] = mapped_column(String(64), nullable=False)
    severity_band: Mapped[str | None] = mapped_column(String(64), nullable=True)
    event_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False)
    excluded_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    confounded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    possible_corporate_action: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    alpha: Mapped[float | None] = mapped_column(Float, nullable=True)
    beta: Mapped[float | None] = mapped_column(Float, nullable=True)
    residual_std: Mapped[float | None] = mapped_column(Float, nullable=True)
    n_estimation_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    car_by_window: Mapped[dict[str, float]] = mapped_column(JSONB, nullable=False, default=dict)
    window_n_by_window: Mapped[dict[str, int]] = mapped_column(JSONB, nullable=False, default=dict)
    daily_ar_by_offset: Mapped[dict[str, float]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    placebo_mean: Mapped[float | None] = mapped_column(Float, nullable=True)
    placebo_std: Mapped[float | None] = mapped_column(Float, nullable=True)
    placebo_percentile: Mapped[float | None] = mapped_column(Float, nullable=True)
    evidence_json: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
