"""Regression test for the real company-duplication bug found 2026-10-31
while re-running `scripts/bootstrap_companies.py` to pick up a backlog
of never-bootstrapped ISINs: a new ISIN sharing an NSE symbol with an
ALREADY-bootstrapped company produced a second, duplicate Company row
(real case: 8KMILES/SECURKLOUD -- a real rename already correctly
captured by the existing company). Reproduces that exact scenario
against a real Postgres session and verifies
`ledgerlight.ingestion.company_dedup.merge_fragmented_groups` resolves
it: the pre-existing, correctly-renamed company survives as canonical,
the newly-created duplicate is deleted, and both of the group's real
ISINs end up under the one canonical company."""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from ledgerlight.ingestion.company_dedup import (
    find_fragmented_groups,
    load_groups,
    merge_fragmented_groups,
)
from ledgerlight.knowledge.models import Company, CompanyIdentifier

pytestmark = pytest.mark.integration


def _insert_price_bar(
    session: Session,
    trade_date: dt.date,
    symbol: str,
    isin: str,
    source_id: str,
    version_id: uuid.UUID,
) -> None:
    session.execute(
        text(
            "INSERT INTO price_bars "
            "(id, source_id, version_id, row_number, trade_date, symbol, series, isin, raw_row) "
            "VALUES (:id, :source_id, :version_id, 1, :trade_date, :symbol, "
            "'EQ', :isin, 'raw')"
        ),
        {
            "id": uuid.uuid4(),
            "source_id": source_id,
            "version_id": version_id,
            "trade_date": trade_date,
            "symbol": symbol,
            "isin": isin,
        },
    )


def _make_version(session: Session, source_id: str) -> uuid.UUID:
    from ledgerlight.db.models import Document, DocumentVersion, Source

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
    return version.id


def test_merge_resolves_real_duplicate_company_from_renamed_isin_group(db_session: Session) -> None:
    """OLD_ISIN traded as TESTOLD, then renamed to TESTNEW -- both real
    ISINs genuinely belong to one company. Simulates the real bug: the
    rename-aware company (TESTNEW, from an earlier bootstrap) already
    exists; a later bootstrap run creates a SECOND company for OLD_ISIN
    alone (unaware TESTNEW's company already covers it)."""
    version_id = _make_version(db_session, "test_bhavcopy_dedup")
    _insert_price_bar(
        db_session,
        dt.date(2016, 1, 1),
        "TESTOLD",
        "INE_TEST_DEDUP_A",
        "test_bhavcopy_dedup",
        version_id,
    )
    _insert_price_bar(
        db_session,
        dt.date(2017, 1, 5),
        "TESTNEW",
        "INE_TEST_DEDUP_A",
        "test_bhavcopy_dedup",
        version_id,
    )
    _insert_price_bar(
        db_session,
        dt.date(2018, 1, 1),
        "TESTNEW",
        "INE_TEST_DEDUP_B",
        "test_bhavcopy_dedup",
        version_id,
    )

    correct_company = Company(display_name="TESTNEW")
    db_session.add(correct_company)
    db_session.flush()
    db_session.add(
        CompanyIdentifier(
            company_id=correct_company.id,
            identifier_type="ISIN",
            value="INE_TEST_DEDUP_B",
            valid_from=dt.date(2018, 1, 1),
            valid_to=None,
        )
    )
    db_session.add(
        CompanyIdentifier(
            company_id=correct_company.id,
            identifier_type="NSE_SYMBOL",
            value="TESTNEW",
            valid_from=dt.date(2017, 1, 5),
            valid_to=None,
        )
    )
    db_session.flush()

    duplicate_company = Company(display_name="TESTOLD")
    db_session.add(duplicate_company)
    db_session.flush()
    db_session.add(
        CompanyIdentifier(
            company_id=duplicate_company.id,
            identifier_type="ISIN",
            value="INE_TEST_DEDUP_A",
            valid_from=dt.date(2016, 1, 1),
            valid_to=None,
        )
    )
    db_session.add(
        CompanyIdentifier(
            company_id=duplicate_company.id,
            identifier_type="NSE_SYMBOL",
            value="TESTOLD",
            valid_from=dt.date(2016, 1, 1),
            valid_to=dt.date(2017, 1, 5),
        )
    )
    db_session.flush()

    groups = load_groups(db_session)
    our_groups = [g for g in groups if set(g.isins) & {"INE_TEST_DEDUP_A", "INE_TEST_DEDUP_B"}]
    assert len(our_groups) == 1, "the real ISINs should group into one company"
    assert set(our_groups[0].isins) == {"INE_TEST_DEDUP_A", "INE_TEST_DEDUP_B"}

    fragmented = find_fragmented_groups(db_session, our_groups)
    assert len(fragmented) == 1

    stats = merge_fragmented_groups(db_session, fragmented)
    db_session.flush()

    assert stats.companies_deleted == 1

    remaining = db_session.scalars(
        select(Company).where(Company.id.in_([correct_company.id, duplicate_company.id]))
    ).all()
    assert len(remaining) == 1
    assert remaining[0].display_name == "TESTNEW"

    identifiers = db_session.scalars(
        select(CompanyIdentifier).where(
            CompanyIdentifier.identifier_type == "ISIN",
            CompanyIdentifier.value.in_(["INE_TEST_DEDUP_A", "INE_TEST_DEDUP_B"]),
        )
    ).all()
    assert {ident.company_id for ident in identifiers} == {remaining[0].id}
