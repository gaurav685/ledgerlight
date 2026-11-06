"""Append-only JSONL audit log for the human review pack's file-backed
review types. Every decision (including a skip) is one appended JSON
line -- never rewritten, never deleted. Resuming after an interruption
means re-running the same command: this module's own `latest_decisions`
reads every line and keeps only the most recent decision per item_id,
so a re-run naturally skips whatever already has one.
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AuditEntry:
    item_id: str
    decision: str
    reviewer: str
    decided_at: str
    note: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_json_line(self) -> str:
        row: dict[str, Any] = {
            "item_id": self.item_id,
            "decision": self.decision,
            "reviewer": self.reviewer,
            "decided_at": self.decided_at,
            "note": self.note,
        }
        row.update(self.extra)
        return json.dumps(row, sort_keys=True)


def append_entry(
    audit_path: Path,
    item_id: str,
    decision: str,
    reviewer: str,
    note: str | None = None,
    extra: dict[str, Any] | None = None,
) -> AuditEntry:
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    entry = AuditEntry(
        item_id=item_id,
        decision=decision,
        reviewer=reviewer,
        decided_at=dt.datetime.now(dt.UTC).isoformat(),
        note=note,
        extra=extra or {},
    )
    with audit_path.open("a", encoding="utf-8") as fh:
        fh.write(entry.to_json_line() + "\n")
    return entry


def read_all_entries(audit_path: Path) -> list[dict[str, Any]]:
    if not audit_path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with audit_path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def latest_decisions(audit_path: Path) -> dict[str, dict[str, Any]]:
    """Last entry per item_id wins -- the real, current decision for
    each item, even if it was re-decided after an earlier skip."""
    latest: dict[str, dict[str, Any]] = {}
    for row in read_all_entries(audit_path):
        latest[row["item_id"]] = row
    return latest


def progress_counts(audit_path: Path) -> dict[str, int]:
    """Counts by decision, over the latest decision per item only
    (not every audit line -- re-decided items are counted once)."""
    counts: dict[str, int] = {}
    for row in latest_decisions(audit_path).values():
        counts[row["decision"]] = counts.get(row["decision"], 0) + 1
    return counts


def counts_by_reviewer(audit_path: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in latest_decisions(audit_path).values():
        counts[row["reviewer"]] = counts.get(row["reviewer"], 0) + 1
    return counts
