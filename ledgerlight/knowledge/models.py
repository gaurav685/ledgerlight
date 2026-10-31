"""Knowledge-store schema (Phase 2): companies, filings, chunks, taxonomy,
events/fields, entities/mentions/links/merges, review queue, labels,
outcomes (skeleton only -- Phase 3 populates), model registry.

Shares `Base` with ledgerlight.db.models so both schemas live in one
Alembic migration history against the same application database (never
a second database -- that split is reserved for Dagster's own storage,
see ADR 0004). Every timestamp is UTC `timestamptz`. Every extracted
value is traceable to (version_id, page_number, char_start, char_end,
extractor_name, extractor_version, confidence) -- see
docs/knowledge/schema.md.
"""

from __future__ import annotations

import datetime as dt
import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ledgerlight.db.models import Base

EMBEDDING_DIM = 384  # bge-small-en-v1.5's native dimension -- see docs/knowledge/retrieval.md


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


# --- Companies -------------------------------------------------------------


class Company(Base):
    """Canonical company record. Identifier history (ISIN/symbol/BSE
    code/CIN, each with validity periods) lives in CompanyIdentifier --
    this table is deliberately thin."""

    __tablename__ = "companies"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    display_name: Mapped[str] = mapped_column(String(256), nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    identifiers: Mapped[list[CompanyIdentifier]] = relationship(back_populates="company")


class CompanyIdentifier(Base):
    """One identifier value for one company over one validity window.
    Bootstrapped from bhavcopy (ISIN + NSE symbol history via price_bars)
    -- see scripts/bootstrap_companies.py -- so a symbol change over time
    produces two rows (old symbol valid_to=change date, new symbol
    valid_from=change date), never an overwrite."""

    __tablename__ = "company_identifiers"
    __table_args__ = (Index("ix_company_identifiers_type_value", "identifier_type", "value"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"), nullable=False)
    identifier_type: Mapped[str] = mapped_column(
        String(32), nullable=False, doc="ISIN | NSE_SYMBOL | BSE_CODE | CIN"
    )
    value: Mapped[str] = mapped_column(String(64), nullable=False)
    valid_from: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    valid_to: Mapped[dt.date | None] = mapped_column(
        Date, nullable=True, doc="NULL = currently valid"
    )

    source_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("document_versions.id"), nullable=True
    )
    source_price_bar_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("price_bars.id"), nullable=True
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    company: Mapped[Company] = relationship(back_populates="identifiers")


class IdentifierWindowCorrection(Base):
    """Audit trail for every real widen-only correction ever applied to a
    `company_identifiers` row's `valid_from` -- see
    `ledgerlight.ingestion.identifier_window_repair`. Append-only: a row
    here is never updated or deleted, so the full correction history for
    any identifier is always reconstructable from this table alone, not
    only from a point-in-time pg_dump backup.

    `identifier_id` is nullable with `ON DELETE SET NULL`, not a hard
    reference: `scripts/migrate_company_dedup.py` legitimately deletes
    and regenerates `company_identifiers` rows (fresh ids) when merging
    duplicate companies, and that must never be blocked by -- or silently
    destroy -- this audit trail. `identifier_type`/`value` are
    denormalized onto this row for exactly that reason, so a correction
    stays self-describing even after its original identifier row is
    gone."""

    __tablename__ = "identifier_window_corrections"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    identifier_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("company_identifiers.id", ondelete="SET NULL"), nullable=True
    )
    identifier_type: Mapped[str] = mapped_column(String(32), nullable=False)
    value: Mapped[str] = mapped_column(String(64), nullable=False)
    old_valid_from: Mapped[dt.date] = mapped_column(Date, nullable=False)
    new_valid_from: Mapped[dt.date] = mapped_column(Date, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    script_name: Mapped[str] = mapped_column(String(128), nullable=False)
    script_version: Mapped[str] = mapped_column(String(32), nullable=False)
    applied_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Filing(Base):
    """Links a document_version to the company/companies it relates to.
    A version may relate to several companies (e.g. an NCLT listing page
    naming several respondents); never duplicates the documents table --
    source_key/retrieval metadata stay in Phase 1's schema."""

    __tablename__ = "filings"
    __table_args__ = (
        UniqueConstraint("version_id", "company_id", name="uq_filings_version_company"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_versions.id"), nullable=False
    )
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"), nullable=False)
    link_method: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        doc="company_identifiers_metadata | document_metadata | filename_pattern | manual",
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


# --- Chunks (retrieval) ------------------------------------------------------


class Chunk(Base):
    """Page-aware chunk: char_start/char_end index into that page's
    document_pages.raw_text -- a chunk never crosses a page boundary (see
    docs/knowledge/retrieval.md). tsv is maintained by a trigger-free
    application-side update (see ledgerlight.knowledge.chunking) rather
    than a generated column, to keep the chunker's tokenization and the
    search tokenization able to diverge deliberately if ever needed."""

    __tablename__ = "chunks"
    __table_args__ = (
        UniqueConstraint(
            "version_id",
            "page_number",
            "char_start",
            "char_end",
            "chunker_version",
            name="uq_chunks_version_page_span_chunker",
        ),
        CheckConstraint("char_end > char_start", name="ck_chunks_char_end_after_start"),
        Index("ix_chunks_tsv", "tsv", postgresql_using="gin"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_versions.id"), nullable=False
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    char_start: Mapped[int] = mapped_column(Integer, nullable=False)
    char_end: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    chunker_version: Mapped[str] = mapped_column(String(32), nullable=False)

    tsv: Mapped[str | None] = mapped_column(TSVECTOR, nullable=True)

    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM), nullable=True)
    embedding_model_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    embedding_model_version: Mapped[str | None] = mapped_column(String(32), nullable=True)

    known_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        doc="Copied from the owning document_version at chunk-creation time -- "
        "the point-in-time retrieval filter (known_at <= as_of) never joins "
        "back to document_versions to avoid drift.",
    )

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


# --- Taxonomy ----------------------------------------------------------------


class TaxonomyVersion(Base):
    __tablename__ = "taxonomy_versions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    version: Mapped[str] = mapped_column(String(16), nullable=False, unique=True)
    loaded_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    source_file_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    event_types: Mapped[list[EventType]] = relationship(back_populates="taxonomy_version")


class EventType(Base):
    """One row per event_type per taxonomy_version -- loaded wholesale
    from data/taxonomy/taxonomy-v*.yaml by scripts/taxonomy_load.py,
    never hand-inserted (see docs/knowledge/taxonomy.md)."""

    __tablename__ = "event_types"
    __table_args__ = (
        UniqueConstraint("taxonomy_version_id", "code", name="uq_event_types_version_code"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    taxonomy_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("taxonomy_versions.id"), nullable=False
    )
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    definition: Mapped[str] = mapped_column(Text, nullable=False)
    required_fields: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    optional_fields: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    severity_rules: Mapped[list[dict[str, object]]] = mapped_column(JSONB, nullable=False)
    detection_approach: Mapped[str] = mapped_column(String(32), nullable=False)
    thresholds: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)

    taxonomy_version: Mapped[TaxonomyVersion] = relationship(back_populates="event_types")


# --- Events ------------------------------------------------------------------


class Event(Base):
    __tablename__ = "events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    event_type_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("event_types.id"), nullable=False)
    company_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("companies.id"), nullable=True)

    event_time: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    known_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    severity: Mapped[str] = mapped_column(String(16), nullable=False, doc="low | medium | high")
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="candidate",
        doc="candidate | verified | rejected | needs_review",
    )

    detector_name: Mapped[str] = mapped_column(String(64), nullable=False)
    detector_version: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)

    supersedes_event_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("events.id"), nullable=True
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    fields: Mapped[list[EventField]] = relationship(back_populates="event")


class EventField(Base):
    __tablename__ = "event_fields"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("events.id"), nullable=False)
    field_name: Mapped[str] = mapped_column(String(64), nullable=False)
    value_json: Mapped[dict[str, object] | list[object] | str | float | None] = mapped_column(
        JSONB, nullable=True
    )
    normalized_value: Mapped[str | None] = mapped_column(Text, nullable=True)

    evidence_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_versions.id"), nullable=False
    )
    evidence_page: Mapped[int] = mapped_column(Integer, nullable=False)
    evidence_char_start: Mapped[int] = mapped_column(Integer, nullable=False)
    evidence_char_end: Mapped[int] = mapped_column(Integer, nullable=False)

    extractor_name: Mapped[str] = mapped_column(String(64), nullable=False)
    extractor_version: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    validation_status: Mapped[str] = mapped_column(
        String(16), nullable=False, doc="validated | failed | unverifiable"
    )

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    event: Mapped[Event] = relationship(back_populates="fields")


# --- Entities ----------------------------------------------------------------


class Entity(Base):
    __tablename__ = "entities"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    entity_type: Mapped[str] = mapped_column(
        String(16), nullable=False, doc="company | person | audit_firm | rating_agency | other"
    )
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("companies.id"), nullable=True, doc="set when entity_type='company'"
    )
    display_name: Mapped[str] = mapped_column(String(256), nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class EntityIdentifier(Base):
    __tablename__ = "entity_identifiers"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    entity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("entities.id"), nullable=False)
    identifier_type: Mapped[str] = mapped_column(
        String(32), nullable=False, doc="DIN | ICAI_FRN | CIN | OTHER"
    )
    value: Mapped[str] = mapped_column(String(64), nullable=False)

    evidence_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("document_versions.id"), nullable=True
    )
    evidence_page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    evidence_char_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    evidence_char_end: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Mention(Base):
    """One surface occurrence of a name/entity-like string in a document,
    with span evidence. Immutable. Resolution to an entity lives in
    EntityLink, so a mention can be re-linked (e.g. after a merge)
    without mutating the mention itself."""

    __tablename__ = "mentions"
    __table_args__ = (
        UniqueConstraint(
            "version_id",
            "page_number",
            "char_start",
            "char_end",
            name="uq_mentions_version_page_span",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_versions.id"), nullable=False
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    char_start: Mapped[int] = mapped_column(Integer, nullable=False)
    char_end: Mapped[int] = mapped_column(Integer, nullable=False)
    surface_text: Mapped[str] = mapped_column(String(512), nullable=False)
    guessed_entity_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class EntityLink(Base):
    """The resolution decision for one mention. A mention may accumulate
    more than one historical link (e.g. relinked after an entity_merge);
    `status` marks which one is currently active."""

    __tablename__ = "entity_links"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    mention_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("mentions.id"), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("entities.id"), nullable=False)
    method: Mapped[str] = mapped_column(
        String(32), nullable=False, doc="exact_identifier | normalized_name | fuzzy | manual"
    )
    score: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class EntityMerge(Base):
    """Reversible merge: source_entity_id's mentions/identifiers are
    treated as target_entity_id's going forward. Reversal sets
    reversed_at/reversed_by; nothing is ever deleted."""

    __tablename__ = "entity_merges"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    source_entity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("entities.id"), nullable=False)
    target_entity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("entities.id"), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    actor: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    reversed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reversed_by: Mapped[str | None] = mapped_column(String(64), nullable=True)


# --- Review queue --------------------------------------------------------


class ReviewQueueItem(Base):
    __tablename__ = "review_queue"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    item_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        doc="event | event_field | entity_link | mention | entity_merge | label_item | other",
    )
    reference_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    reason_code: Mapped[str] = mapped_column(String(64), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="open", doc="open | in_review | resolved | dismissed"
    )
    resolution: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewer: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    resolved_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# --- Labels (silver/gold) for classifier + extraction + entity-resolution
# + retrieval evaluation -- not explicitly named in the Phase 2 brief's
# §2 table list, but required infrastructure for §4's silver/gold
# annotation workflow and the label-review CLI. See
# docs/knowledge/schema.md for why this was added. ------------------------


class LabelItem(Base):
    """One labelled unit: a chunk (or a whole page, if chunk_id is NULL)
    proposed as a given event_type (or 'none'). label_source starts as
    ai_assisted_unreviewed; only a human review (via the label-review
    CLI) can set it to human_reviewed, which is what makes a label GOLD.
    Never set directly by any automated process."""

    __tablename__ = "label_items"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_versions.id"), nullable=False
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("chunks.id"), nullable=True)

    proposed_event_type_code: Mapped[str] = mapped_column(
        String(32), nullable=False, doc="an event_types.code value, or 'none'"
    )
    proposed_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    proposer_name: Mapped[str] = mapped_column(String(64), nullable=False)
    proposer_version: Mapped[str] = mapped_column(String(32), nullable=False)

    label_source: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="ai_assisted_unreviewed",
        doc="ai_assisted_unreviewed | human_reviewed",
    )
    review_status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="pending",
        doc="pending | accepted | corrected | rejected | skipped",
    )
    corrected_event_type_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reviewer: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reviewed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_note: Mapped[str | None] = mapped_column(
        Text, nullable=True, doc="optional free-text note, e.g. recorded on 'skip'"
    )

    split: Mapped[str | None] = mapped_column(
        String(16), nullable=True, doc="dev | validation | test"
    )
    company_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("companies.id"), nullable=True)

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    fields: Mapped[list[LabelItemField]] = relationship(back_populates="label_item")


class LabelItemField(Base):
    """A span-level field-value label attached to a LabelItem (mirrors
    EventField's evidence shape, for the same reason: every value must
    be traceable to a span)."""

    __tablename__ = "label_item_fields"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    label_item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("label_items.id"), nullable=False)
    field_name: Mapped[str] = mapped_column(String(64), nullable=False)
    proposed_value_json: Mapped[dict[str, object] | list[object] | str | float | None] = (
        mapped_column(JSONB, nullable=True)
    )
    proposed_char_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    proposed_char_end: Mapped[int | None] = mapped_column(Integer, nullable=True)

    review_status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    corrected_value_json: Mapped[dict[str, object] | list[object] | str | float | None] = (
        mapped_column(JSONB, nullable=True)
    )
    reviewer: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reviewed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    label_item: Mapped[LabelItem] = relationship(back_populates="fields")


# --- Outcomes (Phase 3 populates; schema + constraints only) -------------


class FeatureDefinition(Base):
    """One versioned feature's own metadata -- Phase 3 Sec4. A feature's
    `name` can be redefined by a later `version` (e.g. a lookback window
    changes); old snapshots keep citing the version they were built
    under, so this table is append-only, never edited in place."""

    __tablename__ = "feature_definitions"
    __table_args__ = (
        UniqueConstraint("name", "version", name="uq_feature_definitions_name_version"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    inputs: Mapped[list[object]] = mapped_column(
        JSONB, nullable=False, doc="source tables/columns this feature reads"
    )
    provenance_tier: Mapped[str] = mapped_column(
        String(16), nullable=False, doc="STRUCTURED | RULE_VERIFIED | EVENT_CANDIDATE"
    )
    as_of_semantics: Mapped[str] = mapped_column(
        Text, nullable=False, doc="the point-in-time rule, e.g. 'month-end close, t<=as_of'"
    )
    lookback_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    track: Mapped[str] = mapped_column(String(16), nullable=False, doc="UNIVERSE | SEED")
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class FeatureSnapshot(Base):
    """One company's full feature vector at one monthly as_of -- Phase 3
    Sec4. `max_input_known_at` is the latest known_at among every input
    this snapshot read, so a leakage check can assert it never exceeds
    `as_of`'s own cutoff. `data_quality_flags` records real per-snapshot
    caveats (e.g. insufficient price history, a right-censored window) --
    never silently dropped or imputed."""

    __tablename__ = "feature_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "as_of",
            "feature_set_version",
            name="uq_feature_snapshots_company_asof_version",
        ),
        Index("ix_feature_snapshots_as_of", "as_of"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"), nullable=False)
    as_of: Mapped[dt.date] = mapped_column(Date, nullable=False)
    feature_set_version: Mapped[str] = mapped_column(String(32), nullable=False)
    values: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    max_input_known_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    data_quality_flags: Mapped[list[object]] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Outcome(Base):
    """Skeleton only -- see ADR 0005. Phase 3 defines real outcome_type
    values and populates this table; Phase 2 creates no rows here."""

    __tablename__ = "outcomes"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("events.id"), nullable=False)
    outcome_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    outcome_value: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    observed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


# --- Model registry --------------------------------------------------------


class ModelRegistryEntry(Base):
    __tablename__ = "model_registry"
    __table_args__ = (
        UniqueConstraint("model_name", "model_version", name="uq_model_registry_name_version"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    model_name: Mapped[str] = mapped_column(String(64), nullable=False)
    model_version: Mapped[str] = mapped_column(String(64), nullable=False)
    artifact_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    training_data_snapshot_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    params_json: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    metrics_json: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
