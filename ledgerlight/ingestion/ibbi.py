"""IBBI NCLT order discovery and ingestion (Phase 3 Sec2.3).

Phase 0/1 had four hand-found IBBI items: one DHFL order, one Jet Airways
order, and two bare case-listing pages (Reliance Capital, Future Retail --
their actual admission orders were never isolated, a documented gap, see
docs/data/seed-universe.md). This module replaces the blind-search
approach with IBBI's own real listing mechanism.

IBBI's `/orders/nclt` page is a plain Drupal "Views" exposed filter: `GET
/orders/nclt?title=<name>&page=<n>` returns a server-rendered HTML table
(class `tb_abg reporttable`, columns Sr.No./Orders Date/Subject/Orders
Remarks) of every order whose subject text contains `<name>` as a
substring, paginated 25 at a time (confirmed directly: without a title
filter the same page shows 1,607+ pages -- IBBI's entire order history --
which is why this module drives the query from the SEED-track company list
rather than ever fetching that unfiltered listing). No robots.txt exists
on ibbi.gov.in (a direct fetch returns the site's own "Not Found" error
page, not a 200 with rules) -- treated as "no restriction stated", the
same convention `ledgerlight.acquisition.robots.RobotsCache` already
applies, not a licence to ignore the site's structure.

IBBI's title search is a substring match on the order's own "In the
matter of <company> [<case ref>]" subject line, so it also returns
unrelated entities that merely share a word (confirmed real case: a
search for "Jet Airways" also returns "Metro Jet Airways Training Pvt.
Ltd."). Each row's extracted company name is therefore passed through the
same `ledgerlight.ingestion.name_matching` floor used for CARE before a
PDF is fetched.
"""

from __future__ import annotations

import datetime as dt
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx
import structlog
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from ledgerlight.acquisition.fetcher import (
    FileTooLargeError,
    HTTPStatusError,
    LoginRedirectError,
    PoliteFetcher,
    RobotsDisallowed,
)
from ledgerlight.acquisition.manifest import CompanyIdentifiers
from ledgerlight.acquisition.robots import RobotsCache
from ledgerlight.ingestion.base import require_enabled_source
from ledgerlight.ingestion.name_matching import name_match_score
from ledgerlight.ingestion.run_tracking import finish_run, start_run
from ledgerlight.ingestion.seed_track import SEED_COMPANY_SEARCH_NAMES
from ledgerlight.ingestion.upsert import upsert_document_version
from ledgerlight.storage.s3_store import ObjectStore

logger = structlog.get_logger(__name__)

BASE_URL = "https://ibbi.gov.in"
ORDERS_ENDPOINT = f"{BASE_URL}/orders/nclt"
MAX_PAGES_PER_COMPANY = 40  # 40 x 25 = 1,000 orders/company -- generous; real max seen is 3 pages

# Same floor as ledgerlight.ingestion.name_matching, applied to the company
# name extracted from each row's "In the matter of <name> [...]" subject,
# not to the raw subject string (which always contains the search term by
# construction of IBBI's own substring search).
_SUBJECT_NAME_PATTERN = re.compile(
    r"^\s*In the matter of\s+(.+?)(?:\s*\[|\s+(?:I\.?A\.?|M\.?A\.?|C\.?P\.?)\s*[\(.]?\s*No)",
    re.IGNORECASE,
)


def _extract_company_name(subject: str) -> str:
    """Pulls the company name out of a real subject string such as
    'In the matter of Jet Airways (India) Ltd. [IA No. 5729 of 2025 in
    CP (IB) No. 2205 of 2019]'. Falls back to the whole subject (which
    will then simply score low against any seed name) if the pattern
    doesn't match -- never raises on an unexpected real-world format."""
    match = _SUBJECT_NAME_PATTERN.match(subject)
    return match.group(1).strip() if match else subject.strip()


@dataclass
class IbbiDiscoveryStats:
    companies_queried: int = 0
    companies_matched: int = 0
    companies_unmatched: list[str] = field(default_factory=list)
    rows_seen: int = 0
    rows_name_rejected: int = 0
    attempted: int = 0
    fetched_new: int = 0
    unchanged: int = 0
    blocked: int = 0
    errors: list[str] = field(default_factory=list)


class _IbbiDiscoveryClient:
    """Plain GET client for IBBI's Drupal Views order listing -- no
    session/CSRF handling needed (unlike SEBI's AJAX pagination), since
    this listing is server-rendered on each GET including subsequent
    pages. Kept separate from PoliteFetcher for the same reason as
    ledgerlight.ingestion.care's discovery client: these are listing
    fetches, not document downloads."""

    def __init__(self, contact_email: str, rate_limit_seconds: float = 2.0) -> None:
        self._user_agent = f"LedgerlightAcquisition/0.1 (contact: {contact_email})"
        self._client = httpx.Client(timeout=30.0, follow_redirects=True)
        self._robots = RobotsCache(self._user_agent, self._client)
        self._rate_limit_seconds = rate_limit_seconds
        self._last_request_at: float | None = None

    def close(self) -> None:
        self._client.close()

    def _wait(self) -> None:
        if self._last_request_at is not None:
            elapsed = time.monotonic() - self._last_request_at
            remaining = self._rate_limit_seconds - elapsed
            if remaining > 0:
                time.sleep(remaining)
        self._last_request_at = time.monotonic()

    def fetch_listing_page(self, title: str, page: int) -> list[dict[str, Any]]:
        if not self._robots.is_allowed(ORDERS_ENDPOINT):
            raise RobotsDisallowed(ORDERS_ENDPOINT)
        self._wait()
        resp = self._client.get(
            ORDERS_ENDPOINT,
            params={"title": title, "page": page},
            headers={"User-Agent": self._user_agent},
        )
        resp.raise_for_status()
        return _parse_order_rows(resp.text)


def _parse_order_rows(html: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", class_="reporttable")
    if table is None:
        return []
    rows: list[dict[str, Any]] = []
    tbody = table.find("tbody")
    if tbody is None:
        return []
    for tr in tbody.find_all("tr"):
        cells = tr.find_all("td")
        if len(cells) < 4:
            continue
        link = cells[2].find("a")
        if link is None or not link.get("href"):
            continue
        date_text = cells[1].get_text(strip=True)
        try:
            order_date = dt.datetime.strptime(date_text, "%d %b, %Y").date()
        except ValueError:
            order_date = None
        subject = link.get_text(separator=" ", strip=True)
        rows.append(
            {
                "subject": subject,
                "company_name": _extract_company_name(subject),
                "href": link["href"],
                "date_text": date_text,
                "order_date": order_date,
                "category": cells[3].get_text(strip=True),
            }
        )
    return rows


def _paginate_all_rows(client: _IbbiDiscoveryClient, search_name: str) -> list[dict[str, Any]]:
    """Real, demonstrated IBBI behaviour (confirmed 2026-10-28): a page
    within range returns a real or empty results table, but a page
    PAST the last one returns a hard HTTP 404, not an empty table (seen
    for every company whose results spanned more than one page -- e.g.
    Jet Airways's real pages 0-2 each returned rows, and only page 3
    404'd). A 404 here is therefore the pagination end signal, exactly
    like an empty table, and must not discard the rows already
    collected from the pages that succeeded before it."""
    all_rows: list[dict[str, Any]] = []
    for page in range(MAX_PAGES_PER_COMPANY):
        try:
            rows = client.fetch_listing_page(search_name, page)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                break
            raise
        if not rows:
            break
        all_rows.extend(rows)
    return all_rows


def _discover_with_counts(
    client: _IbbiDiscoveryClient, search_name: str
) -> tuple[int, list[dict[str, Any]]]:
    all_rows = _paginate_all_rows(client, search_name)
    matched_rows = [
        row for row in all_rows if name_match_score(search_name, row["company_name"]) >= 75.0
    ]
    return len(all_rows), matched_rows


def discover_orders_for_company(
    client: _IbbiDiscoveryClient, search_name: str
) -> list[dict[str, Any]]:
    """Paginates through every page of IBBI's title-filtered listing for
    `search_name`, returning only rows whose extracted company name
    actually matches (see module docstring on the substring-search false
    positives this excludes)."""
    _total, matched_rows = _discover_with_counts(client, search_name)
    return matched_rows


def run_ibbi_discovery_job(
    session: Session,
    store: ObjectStore,
    fetcher: PoliteFetcher,
    contact_email: str,
    *,
    seed_companies: list[tuple[str, CompanyIdentifiers]] | None = None,
) -> IbbiDiscoveryStats:
    require_enabled_source(session, "ibbi")
    stats = IbbiDiscoveryStats()
    companies = seed_companies if seed_companies is not None else SEED_COMPANY_SEARCH_NAMES
    run = start_run(session, source_id="ibbi", stage="ingest")

    discovery = _IbbiDiscoveryClient(contact_email)
    try:
        for search_name, identifiers in companies:
            stats.companies_queried += 1
            try:
                all_rows, matched_rows = _discover_with_counts(discovery, search_name)
            except Exception as exc:  # noqa: BLE001 - recorded, not swallowed
                stats.errors.append(
                    f"discovery for {search_name!r}: {exc.__class__.__name__}: {exc}"
                )
                continue

            stats.rows_seen += all_rows
            stats.rows_name_rejected += all_rows - len(matched_rows)

            if not matched_rows:
                stats.companies_unmatched.append(search_name)
                continue
            stats.companies_matched += 1

            for row in matched_rows:
                href = row["href"]
                retrieval_url = href if href.startswith("http") else f"{BASE_URL}{quote(href)}"
                stats.attempted += 1
                publication_time = row["order_date"].isoformat() if row["order_date"] else None
                try:
                    entry = fetcher.fetch(
                        source_id="ibbi",
                        source_url=f"{ORDERS_ENDPOINT}?title={quote(search_name)}",
                        retrieval_url=retrieval_url,
                        document_type="nclt_order",
                        licence_status="public_no_explicit_licence",
                        redistribution_allowed="unclear",
                        terms_url=None,
                        company_identifiers=identifiers,
                        publication_time=publication_time,
                        coverage_note=(
                            f"IBBI NCLT order: {row['subject']} "
                            f"(matched seed name {search_name!r} via /orders/nclt title search + "
                            "name-match floor)"
                        ),
                    )
                except RobotsDisallowed:
                    stats.blocked += 1
                    continue
                except (HTTPStatusError, LoginRedirectError, FileTooLargeError) as exc:
                    stats.errors.append(f"{retrieval_url}: {exc.__class__.__name__}: {exc}")
                    continue
                except Exception as exc:  # noqa: BLE001 - recorded, not swallowed
                    stats.errors.append(f"{retrieval_url}: {exc.__class__.__name__}: {exc}")
                    continue

                if entry is None:
                    stats.blocked += 1
                    continue

                body = Path(entry.local_path).read_bytes()
                _version, _doc_new, version_new = upsert_document_version(
                    session, store, entry, body
                )
                if version_new:
                    stats.fetched_new += 1
                else:
                    stats.unchanged += 1
    finally:
        discovery.close()

    finish_run(
        session,
        run,
        status="success" if not stats.errors else "partial_failure",
        fetched=stats.attempted,
        new=stats.fetched_new,
        unchanged=stats.unchanged,
        failed=len(stats.errors),
    )
    return stats
