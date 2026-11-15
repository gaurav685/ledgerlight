"""Tests for ledgerlight.ingestion.care -- the Phase 3 Sec2.2 CARE Ratings
rationale discovery job. The pure matching/discovery logic is tested
without any DB or network (respx-mocked HTTP only); the full
discover-then-fetch-then-upsert path is one integration test against
the real Postgres + Garage dev stack (skipped cleanly if it isn't up),
mirroring tests/test_upsert_content_identity.py's pattern.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import httpx
import pytest
import respx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ledgerlight.acquisition.fetcher import PoliteFetcher, RobotsDisallowed
from ledgerlight.acquisition.manifest import CompanyIdentifiers
from ledgerlight.db.models import Document, DocumentVersion
from ledgerlight.ingestion.care import (
    BASE_URL,
    PRDOCUMENT_ENDPOINT,
    PRYEAR_ENDPOINT,
    SEARCH_ENDPOINT,
    CareDiscoveryStats,
    _CareDiscoveryClient,
    discover_pr_documents_for_company,
    run_care_discovery_job,
)

ROBOTS_URL = f"{BASE_URL}/robots.txt"


def _allow_robots() -> None:
    respx.get(ROBOTS_URL).mock(return_value=httpx.Response(200, text="User-agent: *\nDisallow:\n"))


@respx.mock
def test_discover_pr_documents_for_company_real_shape() -> None:
    _allow_robots()
    respx.get(SEARCH_ENDPOINT).mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [{"CompanyID": "zcS==", "CompanyName": "DHFL Holdings Private Limited"}],
                "report": [],
            },
        )
    )
    respx.get(PRYEAR_ENDPOINT).mock(
        return_value=httpx.Response(200, json={"data": [{"PublishedDate": "2013"}]})
    )
    respx.get(PRDOCUMENT_ENDPOINT).mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "PRDocument": [
                            {
                                "FileTitle": "DHFL Holdings Pvt. Ltd.",
                                "FileURL": "DHFL HOLDINGS PRIVATE LIMITED-04082013.pdf",
                                "PublishedDate": "2013-04-08 00:00:00.000",
                            }
                        ]
                    }
                ]
            },
        )
    )

    client = _CareDiscoveryClient("test@example.com", rate_limit_seconds=0.0)
    try:
        matched, documents = discover_pr_documents_for_company(client, "DHFL Holdings")
    finally:
        client.close()

    assert matched is not None
    assert matched["CompanyName"] == "DHFL Holdings Private Limited"
    assert len(documents) == 1
    assert documents[0]["FileURL"] == "DHFL HOLDINGS PRIVATE LIMITED-04082013.pdf"


@respx.mock
def test_discover_pr_documents_no_match_returns_empty_not_an_error() -> None:
    _allow_robots()
    respx.get(SEARCH_ENDPOINT).mock(
        return_value=httpx.Response(200, json={"data": [], "report": []})
    )

    client = _CareDiscoveryClient("test@example.com", rate_limit_seconds=0.0)
    try:
        matched, documents = discover_pr_documents_for_company(client, "Nonexistent Company Xyz")
    finally:
        client.close()

    assert matched is None
    assert documents == []


@respx.mock
def test_discovery_respects_robots_disallow() -> None:
    respx.get(ROBOTS_URL).mock(
        return_value=httpx.Response(200, text="User-agent: *\nDisallow: /header/\n")
    )
    client = _CareDiscoveryClient("test@example.com", rate_limit_seconds=0.0)
    try:
        with pytest.raises(RobotsDisallowed):
            client.search_companies("Gensol Engineering")
    finally:
        client.close()


@pytest.mark.integration
@respx.mock
def test_run_care_discovery_job_end_to_end(
    db_session: Session, object_store, tmp_path: Path
) -> None:
    repo_root = Path(__file__).resolve().parent.parent
    from ledgerlight.ingestion.sources_sync import sync_sources

    sync_sources(db_session, repo_root / "data" / "manifests" / "sources.yaml")
    store = object_store

    _allow_robots()
    pdf_name = f"TEST_COMPANY-{uuid.uuid4().hex}.pdf"
    respx.get(SEARCH_ENDPOINT).mock(
        return_value=httpx.Response(
            200,
            json={"data": [{"CompanyID": "testid==", "CompanyName": "Test Seed Company Ltd"}]},
        )
    )
    respx.get(PRYEAR_ENDPOINT).mock(
        return_value=httpx.Response(200, json={"data": [{"PublishedDate": "2024"}]})
    )
    respx.get(PRDOCUMENT_ENDPOINT).mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "PRDocument": [
                            {
                                "FileTitle": "Test rationale",
                                "FileURL": pdf_name,
                                "PublishedDate": "2024-01-15 00:00:00.000",
                            }
                        ]
                    }
                ]
            },
        )
    )
    pdf_url = f"{BASE_URL}/upload/CompanyFiles/PR/{pdf_name}"
    respx.get(pdf_url).mock(
        return_value=httpx.Response(
            200, content=b"%PDF-1.4 test content", headers={"content-type": "application/pdf"}
        )
    )

    with PoliteFetcher(
        contact_email="test@example.com",
        data_dir=tmp_path / "data",
        manifest_path=tmp_path / "data" / "manifests" / "care-test.jsonl",
        rate_limit_seconds=0.0,
    ) as fetcher:
        stats = run_care_discovery_job(
            db_session,
            store,
            fetcher,
            "test@example.com",
            seed_companies=[("Test Seed Company", CompanyIdentifiers(nse_symbol="TESTCO"))],
        )

    assert isinstance(stats, CareDiscoveryStats)
    assert stats.companies_matched == 1
    assert stats.documents_discovered == 1
    assert stats.fetched_new == 1
    assert stats.errors == []

    document = db_session.scalar(
        select(Document).where(Document.source_id == "care", Document.source_key == pdf_url)
    )
    assert document is not None
    assert document.nse_symbol == "TESTCO"
    version = db_session.scalar(
        select(DocumentVersion).where(DocumentVersion.document_id == document.id)
    )
    assert version is not None
