"""feature_definitions and feature_snapshots tables

Revision ID: 52959e2bb0c4
Revises: 61708ede1bba
Create Date: 2026-10-31 00:41:21.448731

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "52959e2bb0c4"
down_revision: str | Sequence[str] | None = "61708ede1bba"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "feature_definitions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("inputs", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("provenance_tier", sa.String(length=16), nullable=False),
        sa.Column("as_of_semantics", sa.Text(), nullable=False),
        sa.Column("lookback_days", sa.Integer(), nullable=True),
        sa.Column("track", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", "version", name="uq_feature_definitions_name_version"),
    )
    op.create_table(
        "feature_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("feature_set_version", sa.String(length=32), nullable=False),
        sa.Column("values", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("max_input_known_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("data_quality_flags", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id",
            "as_of",
            "feature_set_version",
            name="uq_feature_snapshots_company_asof_version",
        ),
    )
    op.create_index("ix_feature_snapshots_as_of", "feature_snapshots", ["as_of"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_feature_snapshots_as_of", table_name="feature_snapshots")
    op.drop_table("feature_snapshots")
    op.drop_table("feature_definitions")
