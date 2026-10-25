"""Sync data/manifests/sources.yaml into the `sources` table.

A source is `enabled` if and only if its verdict is AVAILABLE or
AVAILABLE_WITH_LIMITS. Every other verdict (BLOCKED,
REQUIRES_PAYMENT_OR_LICENCE, REQUIRES_REGISTRATION, AWAITING_KEY, UNCLEAR)
is synced as `enabled=False` — see ledgerlight.ingestion.base for the
runtime enforcement that makes a disabled source impossible to schedule.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from sqlalchemy.orm import Session

from ledgerlight.common.timeutil import utc_now
from ledgerlight.db.models import Source

SCHEDULABLE_VERDICTS = frozenset({"AVAILABLE", "AVAILABLE_WITH_LIMITS"})


def sync_sources(session: Session, sources_yaml_path: Path) -> list[str]:
    """Upsert every source in sources.yaml. Returns the list of source IDs synced."""
    data = yaml.safe_load(sources_yaml_path.read_text(encoding="utf-8"))
    now = utc_now()
    synced: list[str] = []

    for source_id, entry in data["sources"].items():
        verdict = entry.get("verdict", "UNCLEAR")
        enabled = verdict in SCHEDULABLE_VERDICTS

        rate_limit = entry.get("rate_limit_seconds")
        terms_url = (
            entry.get("terms_of_use", {}).get("url")
            if isinstance(entry.get("terms_of_use"), dict)
            else None
        )
        robots = entry.get("robots_txt")
        robots_status = None
        if isinstance(robots, dict):
            robots_status = robots.get("result") or robots.get("quoted") or robots.get("note")

        existing = session.get(Source, source_id)
        if existing is None:
            session.add(
                Source(
                    id=source_id,
                    verdict=verdict,
                    enabled=enabled,
                    rate_limit_seconds=rate_limit,
                    terms_url=terms_url,
                    robots_status=robots_status,
                    synced_at=now,
                )
            )
        else:
            existing.verdict = verdict
            existing.enabled = enabled
            existing.rate_limit_seconds = rate_limit
            existing.terms_url = terms_url
            existing.robots_status = robots_status
            existing.synced_at = now
        synced.append(source_id)

    session.commit()
    return synced
