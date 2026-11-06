"""Phase 6A §12: generate docs/data-dictionary.md from the real, live
SQLAlchemy model metadata -- never hand-written, so it can't drift from
the actual schema. Run after any model change and recommit the output.

Usage:
    uv run python scripts/generate_data_dictionary.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
OUT_PATH = REPO_ROOT / "docs" / "data-dictionary.md"

# Import every module that defines ORM models so Base.metadata is fully
# populated before introspecting it -- found by grepping for `class X(Base):`
# across the codebase.
from sqlalchemy import CheckConstraint, UniqueConstraint  # noqa: E402

import ledgerlight.agent.models  # noqa: F401,E402
import ledgerlight.api.models  # noqa: F401,E402
import ledgerlight.knowledge.models  # noqa: F401,E402
from ledgerlight.db.models import Base  # noqa: E402


def _type_str(column) -> str:  # type: ignore[no-untyped-def]
    try:
        return str(column.type)
    except Exception:  # noqa: BLE001 - some dialect-specific types repr oddly
        return type(column.type).__name__


def main() -> int:
    tables = sorted(Base.metadata.tables.values(), key=lambda t: t.name)

    lines: list[str] = [
        "# Data dictionary",
        "",
        "Generated from the real, live SQLAlchemy model metadata by "
        "`scripts/generate_data_dictionary.py` -- never hand-written. "
        f"{len(tables)} real tables, as of this run. Regenerate after any "
        "model change; do not hand-edit this file.",
        "",
    ]

    for table in tables:
        lines.append(f"## `{table.name}`")
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
