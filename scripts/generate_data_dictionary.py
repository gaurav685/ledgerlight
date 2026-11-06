"""Phase 6A §12: generate docs/data-dictionary.md from the real, live
database schema -- never hand-written, so it can't drift from the
actual schema. Reflects the live database directly (not just imported
SQLAlchemy models): a real gap found while verifying this script
against a truly from-scratch migrated database (Phase 6A §13's
clean-install test) is that `rate_limit_counters` has no ORM model at
all -- `ledgerlight.api.rate_limit` only ever touches it via raw SQL
-- so reading `Base.metadata` alone (this script's first version)
silently missed it. Reflecting the live database instead covers any
table, ORM-backed or not.

Requires a running local Postgres with migrations applied (`uv run
alembic upgrade head`) -- this project already assumes that for
nearly everything else.

Usage:
    uv run python scripts/generate_data_dictionary.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
OUT_PATH = REPO_ROOT / "docs" / "data-dictionary.md"

import pgvector.sqlalchemy  # noqa: F401,E402 - registers the real `vector` type for reflection
from sqlalchemy import CheckConstraint, MetaData, UniqueConstraint  # noqa: E402

from ledgerlight.config.settings import load_settings  # noqa: E402
from ledgerlight.db.session import make_engine  # noqa: E402

# Alembic's own internal bookkeeping table -- not part of this
# project's real schema, excluded from the dictionary.
_EXCLUDED_TABLES = {"alembic_version"}

# Real tables with no SQLAlchemy ORM model at all (accessed only via
# raw SQL) -- reflection still finds their real columns/types/PK from
# the live database; this set only controls the disclosure note.
_NO_ORM_MODEL = {"rate_limit_counters"}


def _type_str(column) -> str:  # type: ignore[no-untyped-def]
    try:
        return str(column.type)
    except Exception:  # noqa: BLE001 - some dialect-specific types repr oddly
        return type(column.type).__name__


def main() -> int:
    settings = load_settings()
    engine = make_engine(settings)
    metadata = MetaData()
    metadata.reflect(bind=engine)

    tables = sorted(
        (t for t in metadata.tables.values() if t.name not in _EXCLUDED_TABLES),
        key=lambda t: t.name,
    )

    lines: list[str] = [
        "# Data dictionary",
        "",
        "Generated from the real, live database schema (reflected directly, "
        "not just imported SQLAlchemy models -- see this script's own "
        "docstring for why) by `scripts/generate_data_dictionary.py` -- "
        f"never hand-written. {len(tables)} real tables, as of this run "
        "(excludes Alembic's own `alembic_version` bookkeeping table). "
        "Regenerate after any schema change; do not hand-edit this file.",
        "",
    ]

    for table in tables:
        lines.append(f"## `{table.name}`")
        lines.append("")
        if table.name in _NO_ORM_MODEL:
            lines.append(
                "*No SQLAlchemy ORM model -- accessed only via raw SQL "
                "(see the table's own creating migration for why).*"
            )
            lines.append("")
        lines.append("| column | type | nullable | default | key |")
        lines.append("|---|---|---|---|---|")
        pk_cols = {c.name for c in table.primary_key.columns}
        for col in table.columns:
            key_bits = []
            if col.name in pk_cols:
                key_bits.append("PK")
            for fk in col.foreign_keys:
                key_bits.append(f"FK -> `{fk.column.table.name}.{fk.column.name}`")
            if col.unique:
                key_bits.append("UNIQUE")
            default = ""
            if col.server_default is not None:
                default = str(getattr(col.server_default, "arg", col.server_default))
            elif col.default is not None:
                arg = getattr(col.default, "arg", col.default)
                default = arg.__name__ if callable(arg) else str(arg)
            lines.append(
                f"| `{col.name}` | {_type_str(col)} | "
                f"{'yes' if col.nullable else 'no'} | {default} | "
                f"{', '.join(key_bits)} |"
            )
        if table.indexes:
            lines.append("")
            lines.append(
                "Indexes: " + ", ".join(sorted(ix.name for ix in table.indexes if ix.name))
            )
        uniques = [c for c in table.constraints if isinstance(c, UniqueConstraint)]
        checks = [c for c in table.constraints if isinstance(c, CheckConstraint)]
        if uniques:
            lines.append("")
            lines.append(
                "Unique constraints: "
                + ", ".join("(" + ", ".join(col.name for col in u.columns) + ")" for u in uniques)
            )
        if checks:
            lines.append("")
            lines.append("Check constraints: " + ", ".join(str(c.sqltext) for c in checks))
        lines.append("")

    OUT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {OUT_PATH} -- {len(tables)} tables")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
