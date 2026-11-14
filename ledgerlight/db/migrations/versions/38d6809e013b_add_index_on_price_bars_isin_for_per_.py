"""add index on price_bars isin for per-isin lookups

Revision ID: 38d6809e013b
Revises: c44df97d6b30
Create Date: 2026-11-13 23:12:46.494999

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "38d6809e013b"
down_revision: str | Sequence[str] | None = "c44df97d6b30"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Real pre-existing gap found during Enhancement 1 Correction §1.2:
    # price_bars had no index at all on isin, so every per-ISIN lookup
    # (load_eq_closes_by_isin -- WHERE isin = $1 ... ORDER BY trade_date)
    # did a full sequential scan of all ~3.06M real rows. Composite on
    # (isin, trade_date) covers both the filter and the ORDER BY.
    op.create_index(
        "ix_price_bars_isin_trade_date",
        "price_bars",
        ["isin", "trade_date"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_price_bars_isin_trade_date", table_name="price_bars")
