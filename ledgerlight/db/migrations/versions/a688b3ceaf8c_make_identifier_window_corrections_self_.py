"""make identifier_window_corrections self-describing and FK-safe on delete

Revision ID: a688b3ceaf8c
Revises: 40592218ac8b
Create Date: 2026-10-31 15:57:02.572086

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a688b3ceaf8c"
down_revision: str | Sequence[str] | None = "40592218ac8b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add nullable first -- the table already has rows from the live repair
    # run, and there is no sane literal default for identifier_type/value.
    op.add_column(
        "identifier_window_corrections", sa.Column("identifier_type", sa.String(length=32))
    )
    op.add_column("identifier_window_corrections", sa.Column("value", sa.String(length=64)))

    # Backfill from the still-intact company_identifiers rows before this
    # migration's own FK change makes that join unreliable for any future
    # deletion.
    op.execute(
        "UPDATE identifier_window_corrections iwc "
        "SET identifier_type = ci.identifier_type, value = ci.value "
        "FROM company_identifiers ci "
        "WHERE ci.id = iwc.identifier_id"
    )

    op.alter_column("identifier_window_corrections", "identifier_type", nullable=False)
    op.alter_column("identifier_window_corrections", "value", nullable=False)

    op.alter_column(
        "identifier_window_corrections",
        "identifier_id",
        existing_type=sa.Uuid(),
        nullable=True,
    )
    op.drop_constraint(
        "identifier_window_corrections_identifier_id_fkey",
        "identifier_window_corrections",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "identifier_window_corrections_identifier_id_fkey",
        "identifier_window_corrections",
        "company_identifiers",
        ["identifier_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        "identifier_window_corrections_identifier_id_fkey",
        "identifier_window_corrections",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "identifier_window_corrections_identifier_id_fkey",
        "identifier_window_corrections",
        "company_identifiers",
        ["identifier_id"],
        ["id"],
    )
    op.alter_column(
        "identifier_window_corrections",
        "identifier_id",
        existing_type=sa.Uuid(),
        nullable=False,
    )
    op.drop_column("identifier_window_corrections", "value")
    op.drop_column("identifier_window_corrections", "identifier_type")
