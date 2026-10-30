"""Tests for ledgerlight.ingestion.ibbi -- the Phase 3 Sec2.3 IBBI NCLT
order discovery job. Pure parsing/discovery logic is tested without any
DB or network (respx-mocked HTTP, with real HTML fixtures taken from
actual IBBI responses); the full discover-then-fetch-then-upsert path is
one integration test against the real Postgres + Garage dev stack
(skipped cleanly if it isn't up), mirroring tests/test_care_ingestion.py.
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
from ledgerlight.ingestion.ibbi import (
    BASE_URL,
    ORDERS_ENDPOINT,
    IbbiDiscoveryStats,
    _extract_company_name,
    _IbbiDiscoveryClient,
    _parse_order_rows,
    discover_orders_for_company,
    run_ibbi_discovery_job,
)

ROBOTS_URL = f"{BASE_URL}/robots.txt"

# A trimmed, real fixture shape -- two genuine rows (one real Jet Airways
# order, one unrelated subsidiary IBBI's own substring search also
# returns) -- matching the actual table markup fetched 2026-10-28.
REAL_SHAPE_HTML = """
<table class="cols-4 tb_abg reporttable">
  <thead>
    <tr><th>Sr.No.</th><th>Orders Date</th><th>Subject</th><th>Orders Remarks</th></tr>
  </thead>
  <tbody>
    <tr>
      <td>1</td>
      <td>10 Jul, 2026</td>
      <td><a href=/uploads/order/f5303d59ab1526373de5dd399230a1fb.pdf download>In the matter of
        Jet Airways (India) Ltd. [IA No. 5729 of 2025 in CP (IB) No. 2205 of 2019]&nbsp;
        <img src="/img/pdf.jpg" width="15">(350.62 KB)</a></td>
      <td>Others</td>
    </tr>
    <tr>
      <td>2</td>
      <td>08 Jul, 2026</td>
      <td><a href=/uploads/order/b3aa7d196b7c46f94513cd6e609c7000.pdf download>In the matter of
        Metro Jet Airways Training Pvt. Ltd. [IA No. 640 & 641-JPR-2023 in CP No.
        (IB)-176-9-JPR-2019]&nbsp;</a></td>
      <td>Others</td>
    </tr>
  </tbody>
</table>
"""

NO_RESULTS_HTML = """
<table class="cols-4 tb_abg reporttable">
  <thead>
    <tr><th>Sr.No.</th><th>Orders Date</th><th>Subject</th><th>Orders Remarks</th></tr>
  </thead>
  <tbody>
    <tr><td colspan="4">No Records Found</td></tr>
  </tbody>
</table>
"""


def _allow_robots() -> None:
    respx.get(ROBOTS_URL).mock(return_value=httpx.Response(200, text="User-agent: *\nDisallow:\n"))


def test_extract_company_name_from_real_subject() -> None:
    subject = (
        "In the matter of Jet Airways (India) Ltd. "
        "[IA No. 5729 of 2025 in CP (IB) No. 2205 of 2019]"
    )
    assert _extract_company_name(subject) == "Jet Airways (India) Ltd."


def test_parse_order_rows_real_shape() -> None:
    rows = _parse_order_rows(REAL_SHAPE_HTML)
    assert len(rows) == 2
    assert rows[0]["href"] == "/uploads/order/f5303d59ab1526373de5dd399230a1fb.pdf"
    assert rows[0]["company_name"] == "Jet Airways (India) Ltd."
    assert rows[0]["order_date"].isoformat() == "2026-07-10"
    assert rows[1]["company_name"] == "Metro Jet Airways Training Pvt. Ltd."


def test_parse_order_rows_no_results() -> None:
    assert _parse_order_rows(NO_RESULTS_HTML) == []


@respx.mock
def test_discover_orders_for_company_excludes_unrelated_subsidiary() -> None:
    _allow_robots()
    respx.get(ORDERS_ENDPOINT).mock(
        side_effect=[
            httpx.Response(200, text=REAL_SHAPE_HTML),
            httpx.Response(200, text=NO_RESULTS_HTML),
        ]
    )

    client = _IbbiDiscoveryClient("test@example.com", rate_limit_seconds=0.0)
    try:
        matched = discover_orders_for_company(client, "Jet Airways")
    finally:
        client.close()

    assert len(matched) == 1
    assert matched[0]["company_name"] == "Jet Airways (India) Ltd."


@respx.mock
def test_pagination_404_on_out_of_range_page_keeps_earlier_rows() -> None:
    """Real bug (2026-10-28 live run): IBBI returns a hard 404 for a page
    past the last one, not an empty table. The first run's pagination
    loop let that 404 propagate and discarded every row already
    collected from earlier, successful pages -- for every company whose
    results spanned more than one page. This is the regression test."""
    _allow_robots()
    respx.get(ORDERS_ENDPOINT).mock(
        side_effect=[
            httpx.Response(200, text=REAL_SHAPE_HTML),
            httpx.Response(404, text="Not Found"),
        ]
    )

    client = _IbbiDiscoveryClient("test@example.com", rate_limit_seconds=0.0)
    try:
        matched = discover_orders_for_company(client, "Jet Airways")
    finally:
        client.close()

    assert len(matched) == 1
    assert matched[0]["company_name"] == "Jet Airways (India) Ltd."


@respx.mock
def test_discover_orders_no_match_returns_empty() -> None:
    _allow_robots()
    respx.get(ORDERS_ENDPOINT).mock(return_value=httpx.Response(200, text=NO_RESULTS_HTML))

    client = _IbbiDiscoveryClient("test@example.com", rate_limit_seconds=0.0)
    try:
        matched = discover_orders_for_company(client, "Nonexistent Company Xyz")
    finally:
        client.close()

    assert matched == []


@respx.mock
def test_discovery_respects_robots_disallow() -> None:
    respx.get(ROBOTS_URL).mock(
        return_value=httpx.Response(200, text="User-agent: *\nDisallow: /orders/\n")
    )
    client = _IbbiDiscoveryClient("test@example.com", rate_limit_seconds=0.0)
    try:
        with pytest.raises(RobotsDisallowed):
            client.fetch_listing_page("Jet Airways", 0)
    finally:
        client.close()


@pytest.mark.integration
@respx.mock
def test_run_ibbi_discovery_job_end_to_end(db_session: Session, tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parent.parent
    from ledgerlight.config.settings import Settings
    from ledgerlight.ingestion.sources_sync import sync_sources
    from ledgerlight.storage.s3_store import ObjectStore

    settings = Settings(_env_file=str(repo_root / ".env"))  # type: ignore[call-arg]
    sync_sources(db_session, repo_root / "data" / "manifests" / "sources.yaml")
    store = ObjectStore(settings)

    _allow_robots()
    pdf_name = f"{uuid.uuid4().hex}.pdf"
    single_row_html = f"""
<table class="cols-4 tb_abg reporttable">
  <thead><tr><th>Sr.No.</th><th>Orders Date</th><th>Subject</th><th>Orders Remarks</th></tr></thead>
  <tbody>
    <tr>
      <td>1</td>
      <td>15 Jan, 2024</td>
      <td><a href=/uploads/order/{pdf_name} download>In the matter of
        Test Seed Company Ltd. [IA No. 1 of 2024 in CP (IB) No. 1 of 2024]</a></td>
      <td>Others</td>
    </tr>
  </tbody>
</table>
"""
    respx.get(ORDERS_ENDPOINT).mock(
        side_effect=[
            httpx.Response(200, text=single_row_html),
            httpx.Response(200, text=NO_RESULTS_HTML),
        ]
    )
    pdf_url = f"{BASE_URL}/uploads/order/{pdf_name}"
    respx.get(pdf_url).mock(
        return_value=httpx.Response(
            200, content=b"%PDF-1.4 test content", headers={"content-type": "application/pdf"}
        )
    )

    with PoliteFetcher(
        contact_email="test@example.com",
        data_dir=tmp_path / "data",
        manifest_path=tmp_path / "data" / "manifests" / "ibbi-test.jsonl",
        rate_limit_seconds=0.0,
    ) as fetcher:
        stats = run_ibbi_discovery_job(
            db_session,
            store,
            fetcher,
            "test@example.com",
            seed_companies=[("Test Seed Company", CompanyIdentifiers(nse_symbol="TESTCO"))],
        )

    assert isinstance(stats, IbbiDiscoveryStats)
    assert stats.companies_matched == 1
    assert stats.fetched_new == 1
    assert stats.errors == []

    document = db_session.scalar(
        select(Document).where(Document.source_id == "ibbi", Document.source_key == pdf_url)
    )
    assert document is not None
    assert document.nse_symbol == "TESTCO"
    version = db_session.scalar(
        select(DocumentVersion).where(DocumentVersion.document_id == document.id)
    )
    assert version is not None
