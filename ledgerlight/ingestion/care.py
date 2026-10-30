"""CARE Ratings rationale discovery and ingestion (Phase 3 Sec2.2).

Phase 1/2 had exactly one hardcoded CARE item (DHFL, 2019-06-05 -- see
known_seed_items.py). This module broadens that compliantly.

**What was checked and does NOT exist**: a crawlable, sitewide,
date-range listing of rating rationales. `/industry/press-release/24`
(linked from the site's own nav/sitemap) only filters *industry
research* reports by month/year, not company rationales, and is itself
rendered client-side with no discoverable date-range API for that
content. This is reported honestly as a real limitation, not papered
over -- "all rationales ever published" is not reachable this way.

**What DOES exist**, same-origin, and is exactly what the site's own
header search widget calls (confirmed by reading its inline <script>,
not guessed): a per-company lookup --

1. ``GET /header/searchlist?cinput=<name, >=3 chars>`` ->
   ``{"data": [{"CompanyID": <encrypted>, "CompanyName": ...}], ...}``
2. ``GET /pryear?companyName=<encrypted CompanyID>`` -> the years that
   company has press releases for.
3. ``GET /getSearchprdocument?companyName=<encrypted CompanyID>&YearID=<year>``
   -> ``{"data": [{"PRDocument": [{"FileTitle", "FileURL", "PublishedDate", ...}]}]}``,
   where ``FileURL`` is the filename under ``/upload/CompanyFiles/PR/``.

robots.txt is fully permissive (``User-agent: *\\nDisallow:``, confirmed
2026-10-23 in sources.yaml and re-checked 2026-10-28) and this is the
same path a real browser's search box takes -- no fingerprinting
challenge defeated, no auth bypassed.

This module drives that lookup from Ledgerlight's own SEED-track
company list (docs/data/seed-universe.md), rather than crawling
blindly: CARE rates debt instruments, so most of the multi-thousand-
symbol bhavcopy universe will have nothing on file there anyway, and
driving discovery by the companies this project actually has deep
coverage for also directly produces the name->identifier link Sec2.4
asks for, instead of linking separately after the fact.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx
import structlog
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
from ledgerlight.ingestion.name_matching import best_name_match
from ledgerlight.ingestion.run_tracking import finish_run, start_run
from ledgerlight.ingestion.seed_track import SEED_COMPANY_SEARCH_NAMES
from ledgerlight.ingestion.upsert import upsert_document_version
from ledgerlight.storage.s3_store import ObjectStore

logger = structlog.get_logger(__name__)

BASE_URL = "https://www.careratings.com"
SEARCH_ENDPOINT = f"{BASE_URL}/header/searchlist"
PRYEAR_ENDPOINT = f"{BASE_URL}/pryear"
PRDOCUMENT_ENDPOINT = f"{BASE_URL}/getSearchprdocument"
PR_FILE_BASE = f"{BASE_URL}/upload/CompanyFiles/PR/"
TERMS_URL = "https://www.careratings.com/terms-condition"


@dataclass
class CareDiscoveryStats:
    companies_queried: int = 0
    companies_matched: int = 0
    companies_unmatched: list[str] = field(default_factory=list)
    documents_discovered: int = 0
    attempted: int = 0
    fetched_new: int = 0
    unchanged: int = 0
    blocked: int = 0
    errors: list[str] = field(default_factory=list)


class _CareDiscoveryClient:
    """Same-origin JSON-API client for CARE's own header-search widget
    (see module docstring). Kept separate from PoliteFetcher because
    these are discovery API calls, not document downloads -- no
    manifest entry is written for a discovery call itself, only for the
    rationale PDFs it finds, via the same PoliteFetcher.fetch /
    upsert_document_version path every other source uses."""

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

    def _get_json(self, url: str, params: dict[str, str]) -> Any:
        if not self._robots.is_allowed(url):
            raise RobotsDisallowed(url)
        self._wait()
        resp = self._client.get(url, params=params, headers={"User-Agent": self._user_agent})
        resp.raise_for_status()
        return resp.json()

    def search_companies(self, query: str) -> list[dict[str, Any]]:
        if len(query) < 3:
            return []
        data = self._get_json(SEARCH_ENDPOINT, {"cinput": query})
        return data.get("data") or []

    def available_years(self, company_id: str) -> list[str]:
        data = self._get_json(PRYEAR_ENDPOINT, {"companyName": company_id})
        return [
            row["PublishedDate"] for row in (data.get("data") or []) if row.get("PublishedDate")
        ]

    def documents_for_year(self, company_id: str, year: str) -> list[dict[str, Any]]:
        data = self._get_json(PRDOCUMENT_ENDPOINT, {"companyName": company_id, "YearID": year})
        docs: list[dict[str, Any]] = []
        for row in data.get("data") or []:
            docs.extend(row.get("PRDocument") or [])
        return docs


def discover_pr_documents_for_company(
    client: _CareDiscoveryClient, search_name: str
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """Returns (matched_company_record_or_None, documents). documents is
    [] both when there is no name match and when the matched company
    simply has zero PR documents on file -- callers distinguish the two
    via the first element, not by document count alone."""
    candidates = client.search_companies(search_name)
    matched = best_name_match(search_name, candidates, lambda c: c.get("CompanyName", ""))
    if matched is None:
        return None, []
    company_id = matched["CompanyID"]
    documents: list[dict[str, Any]] = []
    for year in client.available_years(company_id):
        documents.extend(client.documents_for_year(company_id, year))
    return matched, documents


def run_care_discovery_job(
    session: Session,
    store: ObjectStore,
    fetcher: PoliteFetcher,
    contact_email: str,
    *,
    seed_companies: list[tuple[str, CompanyIdentifiers]] | None = None,
) -> CareDiscoveryStats:
    require_enabled_source(session, "care")
    stats = CareDiscoveryStats()
    companies = seed_companies if seed_companies is not None else SEED_COMPANY_SEARCH_NAMES
    run = start_run(session, source_id="care", stage="ingest")

    discovery = _CareDiscoveryClient(contact_email)
    try:
        for search_name, identifiers in companies:
            stats.companies_queried += 1
            try:
                matched, documents = discover_pr_documents_for_company(discovery, search_name)
            except Exception as exc:  # noqa: BLE001 - recorded, not swallowed
                stats.errors.append(
                    f"discovery for {search_name!r}: {exc.__class__.__name__}: {exc}"
                )
                continue

            if matched is None:
                stats.companies_unmatched.append(search_name)
                continue
            stats.companies_matched += 1
            stats.documents_discovered += len(documents)

            for doc in documents:
                file_url = doc.get("FileURL")
                if not file_url:
                    continue
                retrieval_url = PR_FILE_BASE + quote(file_url)
                stats.attempted += 1
                published = doc.get("PublishedDate")
                publication_time = published.split(" ")[0] if published else None
                try:
                    entry = fetcher.fetch(
                        source_id="care",
                        source_url=f"{BASE_URL}/search?Id={quote(str(matched['CompanyID']))}",
                        retrieval_url=retrieval_url,
                        document_type="rating_rationale",
                        licence_status="public_no_explicit_licence",
                        redistribution_allowed="unclear",
                        terms_url=TERMS_URL,
                        company_identifiers=identifiers,
                        publication_time=publication_time,
                        coverage_note=(
                            f"CARE rationale/press release: {doc.get('FileTitle', file_url)} "
                            f"(matched seed name {search_name!r} -> CARE company "
                            f"{matched.get('CompanyName')!r} via header/searchlist + pryear + "
                            "getSearchprdocument discovery)"
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
