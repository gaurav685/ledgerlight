"""Tests for ledgerlight.ingestion.sebi -- the Phase 3 Sec2.3 SEBI
enforcement-order discovery job. Fixtures below are trimmed real
response bodies captured 2026-10-28 (see the module docstring for how
the mechanism was found). The full discover-then-fetch-then-upsert path
is one integration test against the real Postgres + Garage dev stack
(skipped cleanly if it isn't up), mirroring the CARE/IBBI test files.
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
from ledgerlight.ingestion.sebi import (
    BASE_URL,
    LISTING_PAGE,
    SEARCH_ENDPOINT,
    SebiDiscoveryStats,
    _resolve_pdf_url,
    _SebiDiscoveryClient,
    run_sebi_discovery_job,
)

ROBOTS_URL = f"{BASE_URL}/robots.txt"

# Real search-result fragment for "Gensol" (captured 2026-10-28, smid=0
# all-categories scope): one direct PDF link, one HTML landing-page link.
REAL_SEARCH_RESULT_HTML = """
<input type='hidden' name='totalpage' value=1 />
<div class='pagination'><p>&nbsp;1 to 2 of 2 records</p></div>
<div class='main_full top_space'><div class='table-scrollable'>
<table class='table table-striped' id='sample_1' role='grid'>
<thead><tr role='row'><th>Date</th><th>Title</th></tr></thead>
<tr role='row' class='odd'><td>Jul 30, 2025</td><td>
<a href='https://www.sebi.gov.in/sebi_data/attachdocs/jul-2025/confirm_order_gensol_engg.pdf'
target="_blank" title="Confirmatory Order in the matter of Gensol Engineering Limited"
class='points'>Confirmatory Order in the matter of Gensol Engineering Limited</a></td></tr>
<tr role='row' class='odd'><td>Apr 15, 2025</td><td>
<a href='https://www.sebi.gov.in/enforcement/orders/apr-2025/interim-order-in-the-matter-of-gensol-engineering-limited_93458.html'
target="_blank" title="Interim Order in the matter of Gensol Engineering Limited"
class='points'>Interim Order in the matter of Gensol Engineering Limited</a></td></tr>
</table></div></div>
<div class='pagination'><p>&nbsp;1 to 2 of 2 records</p></div>
#@#<li><a href='https://www.sebi.gov.in/index.html'>Home</a></li>
"""

NO_RESULTS_HTML = (
    "<div class='pagination'><div class='pagination_inner'>"
    "<p>No record(s) available.</p></div></div>#@#"
)

# Real landing-page fragment (captured 2026-10-28): the PDF is embedded
# in an iframe, not a plain <a href>.
REAL_LANDING_PAGE_HTML = (
    "<iframe src='https://www.sebi.gov.in/web/?file=https://www.sebi.gov.in/sebi_data/"
    "attachdocs/apr-2025/1744719603252_1.pdf' width='100%' "
    'title="Interim Order">Interim Order</iframe>'
)


def _allow_robots() -> None:
    respx.get(ROBOTS_URL).mock(return_value=httpx.Response(200, text="User-agent: *\nDisallow:\n"))


def test_resolve_pdf_url_from_real_iframe_markup() -> None:
    assert (
        _resolve_pdf_url(REAL_LANDING_PAGE_HTML)
        == "https://www.sebi.gov.in/sebi_data/attachdocs/apr-2025/1744719603252_1.pdf"
    )


def test_resolve_pdf_url_returns_none_when_absent() -> None:
    assert _resolve_pdf_url("<p>no iframe here</p>") is None


@respx.mock
def test_search_parses_real_result_shape() -> None:
    _allow_robots()
    respx.get(LISTING_PAGE).mock(return_value=httpx.Response(200, text="<html></html>"))
    respx.post(SEARCH_ENDPOINT).mock(return_value=httpx.Response(200, text=REAL_SEARCH_RESULT_HTML))

    client = _SebiDiscoveryClient("test@example.com", rate_limit_seconds=0.0)
    try:
        rows = client.search("Gensol Engineering")
    finally:
        client.close()

    assert len(rows) == 2
    assert rows[0]["title"] == "Confirmatory Order in the matter of Gensol Engineering Limited"
    assert rows[0]["href"].endswith(".pdf")
    assert rows[0]["order_date"].isoformat() == "2025-07-30"
    assert rows[1]["href"].endswith(".html")


@respx.mock
def test_search_no_results() -> None:
    _allow_robots()
    respx.get(LISTING_PAGE).mock(return_value=httpx.Response(200, text="<html></html>"))
    respx.post(SEARCH_ENDPOINT).mock(return_value=httpx.Response(200, text=NO_RESULTS_HTML))

    client = _SebiDiscoveryClient("test@example.com", rate_limit_seconds=0.0)
    try:
        rows = client.search("Nonexistent Company Xyz")
    finally:
        client.close()

    assert rows == []


@respx.mock
def test_discovery_respects_robots_disallow() -> None:
    respx.get(ROBOTS_URL).mock(
        return_value=httpx.Response(200, text="User-agent: *\nDisallow: /sebiweb/\n")
    )
    client = _SebiDiscoveryClient("test@example.com", rate_limit_seconds=0.0)
    try:
        with pytest.raises(RobotsDisallowed):
            client.search("Gensol Engineering")
    finally:
        client.close()


@pytest.mark.integration
@respx.mock
def test_run_sebi_discovery_job_end_to_end(
    db_session: Session, object_store, tmp_path: Path
) -> None:
    repo_root = Path(__file__).resolve().parent.parent
    from ledgerlight.ingestion.sources_sync import sync_sources

    sync_sources(db_session, repo_root / "data" / "manifests" / "sources.yaml")
    store = object_store

    _allow_robots()
    respx.get(LISTING_PAGE).mock(return_value=httpx.Response(200, text="<html></html>"))
    pdf_name = f"{uuid.uuid4().hex}.pdf"
    landing_url = "https://www.sebi.gov.in/enforcement/orders/test-order.html"
    pdf_url = f"{BASE_URL}/sebi_data/attachdocs/{pdf_name}"
    title_text = "Order in the matter of Test Seed Company Ltd."
    search_html = f"""
<table id='sample_1'><thead><tr><th>Date</th><th>Title</th></tr></thead>
<tr><td>Jan 15, 2024</td><td><a href='{landing_url}' title="{title_text}">
{title_text}</a></td></tr></table>#@#
"""
    respx.post(SEARCH_ENDPOINT).mock(return_value=httpx.Response(200, text=search_html))
    respx.get(landing_url).mock(
        return_value=httpx.Response(200, text=f"<iframe src='{BASE_URL}/web/?file={pdf_url}'>")
    )
    respx.get(pdf_url).mock(
        return_value=httpx.Response(
            200, content=b"%PDF-1.4 test content", headers={"content-type": "application/pdf"}
        )
    )

    with PoliteFetcher(
        contact_email="test@example.com",
        data_dir=tmp_path / "data",
        manifest_path=tmp_path / "data" / "manifests" / "sebi-test.jsonl",
        rate_limit_seconds=0.0,
    ) as fetcher:
        stats = run_sebi_discovery_job(
            db_session,
            store,
            fetcher,
            "test@example.com",
            seed_companies=[("Test Seed Company", CompanyIdentifiers(nse_symbol="TESTCO"))],
        )

    assert isinstance(stats, SebiDiscoveryStats)
    assert stats.companies_matched == 1
    assert stats.fetched_new == 1
    assert stats.errors == []

    document = db_session.scalar(
        select(Document).where(Document.source_id == "sebi", Document.source_key == pdf_url)
    )
    assert document is not None
    assert document.nse_symbol == "TESTCO"
    version = db_session.scalar(
        select(DocumentVersion).where(DocumentVersion.document_id == document.id)
    )
    assert version is not None


@pytest.mark.integration
@respx.mock
def test_run_sebi_discovery_job_resolves_relative_href(
    db_session: Session, object_store, tmp_path: Path
) -> None:
    """Real bug (2026-10-28 live run): some SEBI direct-PDF hrefs are
    relative paths, not absolute URLs (e.g. "/sebi_data/attachdocs/...pdf").
    Passing one straight to httpx as retrieval_url raised
    httpx.UnsupportedProtocol for 42 of 84 real fetch attempts in the
    first run. This is the regression test."""
    repo_root = Path(__file__).resolve().parent.parent
    from ledgerlight.ingestion.sources_sync import sync_sources

    sync_sources(db_session, repo_root / "data" / "manifests" / "sources.yaml")
    store = object_store

    _allow_robots()
    respx.get(LISTING_PAGE).mock(return_value=httpx.Response(200, text="<html></html>"))
    pdf_name = f"{uuid.uuid4().hex}.pdf"
    relative_href = f"/sebi_data/attachdocs/{pdf_name}"
    absolute_pdf_url = f"{BASE_URL}{relative_href}"
    title_text = "Order in the matter of Test Seed Company Ltd."
    search_html = f"""
<table id='sample_1'><thead><tr><th>Date</th><th>Title</th></tr></thead>
<tr><td>Jan 15, 2024</td><td><a href='{relative_href}' title="{title_text}">
{title_text}</a></td></tr></table>#@#
"""
    respx.post(SEARCH_ENDPOINT).mock(return_value=httpx.Response(200, text=search_html))
    respx.get(absolute_pdf_url).mock(
        return_value=httpx.Response(
            200, content=b"%PDF-1.4 test content", headers={"content-type": "application/pdf"}
        )
    )

    with PoliteFetcher(
        contact_email="test@example.com",
        data_dir=tmp_path / "data",
        manifest_path=tmp_path / "data" / "manifests" / "sebi-test2.jsonl",
        rate_limit_seconds=0.0,
    ) as fetcher:
        stats = run_sebi_discovery_job(
            db_session,
            store,
            fetcher,
            "test@example.com",
            seed_companies=[("Test Seed Company", CompanyIdentifiers(nse_symbol="TESTCO"))],
        )

    assert stats.errors == []
    assert stats.fetched_new == 1
    document = db_session.scalar(
        select(Document).where(
            Document.source_id == "sebi", Document.source_key == absolute_pdf_url
        )
    )
    assert document is not None
