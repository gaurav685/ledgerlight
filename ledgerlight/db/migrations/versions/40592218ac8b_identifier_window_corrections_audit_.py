"""identifier_window_corrections audit table

Revision ID: 40592218ac8b
Revises: 52959e2bb0c4
Create Date: 2026-10-31 01:02:05.518488

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "40592218ac8b"
down_revision: str | Sequence[str] | None = "52959e2bb0c4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "identifier_window_corrections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("identifier_id", sa.Uuid(), nullable=False),
        sa.Column("old_valid_from", sa.Date(), nullable=False),
        sa.Column("new_valid_from", sa.Date(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("script_name", sa.String(length=128), nullable=False),
        sa.Column("script_version", sa.String(length=32), nullable=False),
        sa.Column(
            "applied_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["identifier_id"], ["company_identifiers.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("identifier_window_corrections")
