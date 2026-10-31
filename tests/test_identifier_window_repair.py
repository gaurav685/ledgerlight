"""Regression tests for the real stale-`valid_from` bug found while
building Phase 3 Sec4's price-feature engine (2026-10-31): bootstrap is
idempotent, so an identifier that already existed never got its
`valid_from` refreshed after a later bhavcopy backfill added
earlier-dated real price_bars rows. These reproduce that exact
backfill-gap scenario against a real Postgres session, exercising both
`ledgerlight.ingestion.identifier_window_repair`'s pure guard logic and
`scripts.bootstrap_companies.widen_existing_windows`'s root-cause fix
end-to-end."""

from __future__ import annotations

import datetime as dt
import importlib.util
import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from ledgerlight.db.models import Document, DocumentVersion, Source
from ledgerlight.ingestion.identifier_window_repair import check_widen_guard
from ledgerlight.knowledge.models import Company, CompanyIdentifier, IdentifierWindowCorrection

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parent.parent
_SPEC = importlib.util.spec_from_file_location(
    "bootstrap_companies", REPO_ROOT / "scripts" / "bootstrap_companies.py"
)
assert _SPEC is not None and _SPEC.loader is not None
_BOOTSTRAP = importlib.util.module_from_spec(_SPEC)
sys.modules["bootstrap_companies"] = _BOOTSTRAP
_SPEC.loader.exec_module(_BOOTSTRAP)


def _make_version(session: Session, source_id: str) -> DocumentVersion:
    now = dt.datetime.now(dt.UTC)
    session.merge(Source(id=source_id, verdict="AVAILABLE", enabled=True, synced_at=now))
    session.flush()
    document = Document(source_id=source_id, source_key=f"https://example.test/{uuid.uuid4()}")
    session.add(document)
    session.flush()
    version = DocumentVersion(
        document_id=document.id,
        sha256=uuid.uuid4().hex + uuid.uuid4().hex,
        object_key="test.csv",
        bytes=0,
        retrieval_method="automated_fetch",
        retrieval_url="https://example.test/test.csv",
        retrieved_at=now,
        known_at=now,
        known_at_basis="retrieved_at",
        tool_version="test",
    )
    session.add(version)
    session.flush()
    return version


def _insert_price_bar(
    session: Session, version_id: uuid.UUID, trade_date: dt.date, symbol: str, isin: str
) -> uuid.UUID:
    row_id = uuid.uuid4()
    session.execute(
        text(
            "INSERT INTO price_bars "
            "(id, source_id, version_id, row_number, trade_date, symbol, series, isin, raw_row) "
            "VALUES (:id, 'test_bhavcopy', :version_id, 1, :trade_date, :symbol, "
            "'EQ', :isin, 'raw')"
        ),
        {
            "id": row_id,
            "version_id": version_id,
            "trade_date": trade_date,
            "symbol": symbol,
            "isin": isin,
        },
    )
    return row_id


def test_widen_existing_windows_recovers_real_backfill_gap(db_session: Session) -> None:
    """Reproduces the real scenario: bootstrap ran when the earliest
    known trade was 2017-01-05; a later backfill added real rows back
    to 2016-01-01 for the SAME (symbol, isin) pair. Re-running bootstrap
    must widen valid_from to 2016-01-01 and log one correction row."""
    version = _make_version(db_session, "test_bhavcopy")
    isin = "INE_TEST_WIDEN"
    symbol = "TESTWIDEN"

    _insert_price_bar(db_session, version.id, dt.date(2016, 1, 1), symbol, isin)
    _insert_price_bar(db_session, version.id, dt.date(2017, 1, 5), symbol, isin)

    company = Company(display_name=symbol)
    db_session.add(company)
    db_session.flush()
    identifier = CompanyIdentifier(
        company_id=company.id,
        identifier_type="NSE_SYMBOL",
        value=symbol,
        valid_from=dt.date(2017, 1, 5),
        valid_to=None,
    )
    db_session.add(identifier)
    db_session.flush()

    # NOTE: widen_existing_windows scans every company_identifiers row in
    # the real dev database, not just this test's rows (find_stale_windows
    # has no test-scoping hook) -- so widened/skipped are whole-table
    # totals, not 1/0. Assert on this specific identifier instead.
    widened, skipped = _BOOTSTRAP.widen_existing_windows(db_session)
    db_session.flush()
    assert widened >= 1

    db_session.refresh(identifier)
    assert identifier.valid_from == dt.date(2016, 1, 1)

    corrections = db_session.scalars(
        select(IdentifierWindowCorrection).where(
            IdentifierWindowCorrection.identifier_id == identifier.id
        )
    ).all()
    assert len(corrections) == 1
    assert corrections[0].old_valid_from == dt.date(2017, 1, 5)
    assert corrections[0].new_valid_from == dt.date(2016, 1, 1)
    assert corrections[0].script_name == "scripts/bootstrap_companies.py"


def test_widen_existing_windows_skips_real_symbol_reuse(db_session: Session) -> None:
    """A different real company traded under the same symbol in the
    newly-covered period (a different ISIN) -- must NOT widen."""
    version = _make_version(db_session, "test_bhavcopy")
    symbol = "TESTREUSE"

    _insert_price_bar(db_session, version.id, dt.date(2016, 1, 1), symbol, "INE_OLD_COMPANY")
    _insert_price_bar(db_session, version.id, dt.date(2017, 1, 5), symbol, "INE_NEW_COMPANY")

    company = Company(display_name=symbol)
    db_session.add(company)
    db_session.flush()
    identifier = CompanyIdentifier(
        company_id=company.id,
        identifier_type="NSE_SYMBOL",
        value=symbol,
        valid_from=dt.date(2017, 1, 5),
        valid_to=None,
    )
    db_session.add(identifier)
    db_session.flush()

    _widened, skipped = _BOOTSTRAP.widen_existing_windows(db_session)
    db_session.flush()
    assert skipped >= 1

    db_session.refresh(identifier)
    assert identifier.valid_from == dt.date(2017, 1, 5)

    corrections = db_session.scalars(
        select(IdentifierWindowCorrection).where(
            IdentifierWindowCorrection.identifier_id == identifier.id
        )
    ).all()
    assert len(corrections) == 0


def test_check_widen_guard_pure_logic_matches_real_cases() -> None:
    """Pure-function check (no DB) mirroring the two real cases found in
    the live repair run: a clean widen (3MINDIA) and a correctly-skipped
    symbol reuse / mid-gap rename (BHARATFIN/SKSMICRO)."""
    clean_pairs = {
        "3MINDIA": [
            (dt.date(2016, 1, 1), "INE470A01017"),
            (dt.date(2017, 1, 5), "INE470A01017"),
        ]
    }
    result = check_widen_guard(clean_pairs, "3MINDIA", dt.date(2017, 1, 5))
    assert result.ok is True

    reuse_pairs = {
        "BHARATFIN": [
            (dt.date(2016, 1, 1), "SKSMICRO"),
            (dt.date(2017, 1, 5), "BHARATFIN"),
        ]
    }
    result = check_widen_guard(reuse_pairs, "BHARATFIN", dt.date(2017, 1, 5))
    assert result.ok is False
    assert result.reason == "symbol_reuse_paired_value_mismatch"
