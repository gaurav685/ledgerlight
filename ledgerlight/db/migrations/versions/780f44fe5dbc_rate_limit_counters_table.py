"""rate limit counters table

Revision ID: 780f44fe5dbc
Revises: 4dad2cd00443
Create Date: 2026-11-01 16:46:43.099357

Phase 5 §3: a real, Postgres-backed fixed-window rate-limit counter
table (see `docs/adr/0010-rate-limiting.md` for why Postgres-backed
rather than in-process). Not RLS'd -- not real tenant business data,
and never exposed through any real endpoint; only
`ledgerlight.api.rate_limit`'s own atomic UPSERT touches it. The real
`ledgerlight_app` role gets SELECT/INSERT/UPDATE/DELETE on it, same as
every other table that role needs to write.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "780f44fe5dbc"
down_revision: str | Sequence[str] | None = "4dad2cd00443"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "ledgerlight_app"


def upgrade() -> None:
    op.create_table(
        "rate_limit_counters",
        sa.Column("key", sa.String(length=300), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("key"),
    )
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON rate_limit_counters TO {APP_ROLE}")


def downgrade() -> None:
    op.drop_table("rate_limit_counters")
