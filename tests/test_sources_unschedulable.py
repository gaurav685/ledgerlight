"""BLOCKED/REQUIRES_PAYMENT_OR_LICENCE/UNCLEAR sources must be impossible
to schedule — enforced in ledgerlight.ingestion.base.require_enabled_source
and proven here against the real, synced sources table."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from ledgerlight.ingestion.base import SourceNotSchedulableError, require_enabled_source
from ledgerlight.ingestion.sources_sync import SCHEDULABLE_VERDICTS, sync_sources

pytestmark = pytest.mark.integration


def _sources_yaml_path() -> Path:
    return Path(__file__).resolve().parent.parent / "data" / "manifests" / "sources.yaml"


def test_blocked_source_raises(db_session: Session) -> None:
    sync_sources(db_session, _sources_yaml_path())
    db_session.flush()

    from ledgerlight.db.models import Source

    blocked = db_session.query(Source).filter(Source.verdict.notin_(SCHEDULABLE_VERDICTS)).first()
    if blocked is None:
        pytest.skip("no BLOCKED/REQUIRES_PAYMENT_OR_LICENCE/UNCLEAR source in sources.yaml")

    assert blocked.enabled is False
    with pytest.raises(SourceNotSchedulableError):
        require_enabled_source(db_session, blocked.id)


def test_available_source_does_not_raise(db_session: Session) -> None:
    sync_sources(db_session, _sources_yaml_path())
    db_session.flush()

    source = require_enabled_source(db_session, "nse_archives")
    assert source.enabled is True


def test_unknown_source_raises(db_session: Session) -> None:
    with pytest.raises(SourceNotSchedulableError):
        require_enabled_source(db_session, "not_a_real_source_id")
