"""Ingestion metadata schema (Phase 1). Knowledge/entity tables are Phase 2.

Every timestamp column is UTC `timestamptz`. Source-local dates (IST) are
converted explicitly at the point of parsing — see
docs/data/temporal-semantics.md for the one place this is allowed to be
ambiguous (bhavcopy `trade_date`, which is a calendar date, not an instant).
"""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


class Source(Base):
    """Mirrors data/manifests/sources.yaml — synced by scripts/sources_sync.py."""

    __tablename__ = "sources"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    verdict: Mapped[str] = mapped_column(String(32), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    rate_limit_seconds: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    terms_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    robots_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    synced_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    documents: Mapped[list[Document]] = relationship(back_populates="source")


class Document(Base):
    """Logical document identity. Proper company entities arrive in Phase 2 —
    identifiers here are raw strings exactly as the source stated them."""

    __tablename__ = "documents"
    __table_args__ = (UniqueConstraint("source_id", "source_key", name="uq_documents_source_key"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"), nullable=False)
    source_key: Mapped[str] = mapped_column(
        String(1024), nullable=False, doc="Canonical URL or source-native ID"
    )

    bse_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    nse_symbol: Mapped[str | None] = mapped_column(String(32), nullable=True)
    isin: Mapped[str | None] = mapped_column(String(16), nullable=True)
    company_name_raw: Mapped[str | None] = mapped_column(String(256), nullable=True)

    document_type: Mapped[str] = mapped_column(String(64), nullable=False, default="unknown")

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    source: Mapped[Source] = relationship(back_populates="documents")
    versions: Mapped[list[DocumentVersion]] = relationship(back_populates="document")


class DocumentVersion(Base):
    """Immutable. One row per distinct content hash for a document. The same
    URL with new content creates a new version, never an overwrite."""

    __tablename__ = "document_versions"
    __table_args__ = (
        UniqueConstraint("document_id", "sha256", name="uq_document_versions_doc_sha256"),
        Index("ix_document_versions_sha256", "sha256"),
        Index("ix_document_versions_doc_content_sha256", "document_id", "content_sha256"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id"), nullable=False)

    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    content_sha256: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        doc=(
            "Hash of the dedup-relevant content, which may differ from `sha256` "
            "(the raw downloaded bytes) for containers whose wrapper is not "
            "byte-deterministic -- e.g. a single-entry ZIP whose per-entry "
            "timestamp a server regenerates on every request even when the "
            "payload is unchanged. See ledgerlight.ingestion.upsert. NULL for "
            "versions created before this column existed."
        ),
    )
    object_key: Mapped[str] = mapped_column(String(512), nullable=False)
    bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(128), nullable=True)

    retrieval_method: Mapped[str] = mapped_column(String(32), nullable=False)
    retrieval_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)

    retrieved_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    published_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    snapshot_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    known_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    known_at_basis: Mapped[str] = mapped_column(String(16), nullable=False)

    tool_version: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    document: Mapped[Document] = relationship(back_populates="versions")
    pages: Mapped[list[DocumentPage]] = relationship(back_populates="version")


class DocumentPage(Base):
    """One row per extracted page. raw_text is exactly as extracted and
    immutable — Phase 4 citations reference character offsets into it.
    Bumping extractor_version produces new rows; old rows are kept."""

    __tablename__ = "document_pages"
    __table_args__ = (
        UniqueConstraint(
            "version_id",
            "page_number",
            "extractor_version",
            name="uq_document_pages_version_page_extractor",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_versions.id"), nullable=False
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False, doc="1-based")

    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    text_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    char_count: Mapped[int] = mapped_column(Integer, nullable=False)

    extraction_method: Mapped[str] = mapped_column(
        String(16), nullable=False, doc="text_layer|ocr|html"
    )
    ocr_engine: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ocr_engine_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    ocr_mean_confidence: Mapped[float | None] = mapped_column(Numeric(5, 4), nullable=True)
    extractor_version: Mapped[str] = mapped_column(String(32), nullable=False)

    normalized_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    version: Mapped[DocumentVersion] = relationship(back_populates="pages")


class PriceBar(Base):
    """Parsed bhavcopy rows. Upserted on (source_id, trade_date, symbol,
    series): a corrected re-issue of the same trading day updates the row
    and repoints version_id/row_number, rather than duplicating it — the
    original row text is always preserved for provenance."""

    __tablename__ = "price_bars"
    __table_args__ = (
        UniqueConstraint(
            "source_id",
            "trade_date",
            "symbol",
            "series",
            name="uq_price_bars_source_date_symbol_series",
        ),
        Index("ix_price_bars_trade_date", "trade_date"),
        Index("ix_price_bars_symbol", "symbol"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"), nullable=False)
    version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_versions.id"), nullable=False
    )
    row_number: Mapped[int] = mapped_column(
        Integer, nullable=False, doc="1-based row within the source file"
    )

    trade_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    series: Mapped[str] = mapped_column(String(8), nullable=False)
    isin: Mapped[str | None] = mapped_column(String(16), nullable=True)

    # Numeric -> Decimal (never float) for exact price arithmetic.
    open: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    high: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    low: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    close: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    last: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    prev_close: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    volume: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    turnover: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    trades: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    raw_row: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=_utcnow
    )


class PriceAdjustmentFactor(Base):
    """Enhancement 1 Correction §1: one real detected corporate-action
    adjustment factor for one real ISIN. Raw `price_bars` is never
    mutated -- this table, plus `ledgerlight.modelling.price_adjustment`'s
    pure `adjusted_close` function, is the only real adjustment
    mechanism. `evidence_json` carries the real source rows (the prior
    and new real close/date pair) the detection matched against, the
    same `evidence`-carrying discipline as every other RULE-VERIFIED
    extraction in this project (e.g.
    `ledgerlight.modelling.rating_features.RatingObservation`)."""

    __tablename__ = "price_adjustment_factors"
    __table_args__ = (
        UniqueConstraint("isin", "ex_date", name="uq_price_adjustment_factors_isin_exdate"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    isin: Mapped[str] = mapped_column(String(16), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    ex_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    factor: Mapped[Decimal] = mapped_column(Numeric(14, 6), nullable=False)
    method: Mapped[str] = mapped_column(String(32), nullable=False)
    evidence_json: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class IngestionRun(Base):
    """One row per orchestration run (a job execution)."""

    __tablename__ = "ingestion_runs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    source_id: Mapped[str | None] = mapped_column(ForeignKey("sources.id"), nullable=True)
    stage: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="running")
    started_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    fetched: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    new: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unchanged: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ocr_pages: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rows_parsed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rows_quarantined: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class ProcessingAttempt(Base):
    """One row per attempt at a pipeline stage for a given unit of work."""

    __tablename__ = "processing_attempts"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ingestion_runs.id"), nullable=True)
    version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("document_versions.id"), nullable=True
    )
    stage: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    error_class: Mapped[str | None] = mapped_column(String(32), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class DeadLetter(Base):
    """A unit of work that exhausted its retries."""

    __tablename__ = "dead_letters"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    payload_ref: Mapped[str] = mapped_column(String(512), nullable=False)
    stage: Mapped[str] = mapped_column(String(32), nullable=False)
    last_error: Mapped[str] = mapped_column(Text, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    first_failed_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution: Mapped[str | None] = mapped_column(Text, nullable=True)
