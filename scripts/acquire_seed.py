"""Re-run the Phase 0 seed-dataset acquisition reproducibly.

Every item below was individually verified reachable (HTTP 200, correct
content-type) with the project's identifying User-Agent before being added
here — see docs/data/seed-universe.md and docs/data/source-inventory.md for
the robots.txt / terms-of-use findings behind each source_id.

This is Phase 0 scope only: a small, legitimately-sourced seed, not the
Phase 1 ingestion pipeline.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from ledgerlight.acquisition.fetcher import (  # noqa: E402
    FileTooLargeError,
    LoginRedirectError,
    PoliteFetcher,
    RobotsDisallowed,
)
from ledgerlight.acquisition.manifest import CompanyIdentifiers  # noqa: E402
from ledgerlight.config.settings import load_settings  # noqa: E402

# Each entry mirrors ManifestEntry's provenance fields. licence_status /
# redistribution_allowed reflect docs/data/source-inventory.md: none of
# these sources state an explicit redistribution licence, so Ledgerlight
# treats them as "public, no explicit licence" / redistribution "unclear"
# and never redistributes the downloaded files themselves (only manifests
# are committed).
SEED_ITEMS: list[dict[str, Any]] = [
    {
        "source_id": "sebi",
        "source_url": "https://www.sebi.gov.in/enforcement/orders/apr-2025/interim-order-in-the-matter-of-gensol-engineering-limited_93458.html",
        "retrieval_url": "https://www.sebi.gov.in/sebi_data/attachdocs/apr-2025/1744719603252_1.pdf",
        "document_type": "sebi_interim_order",
        "company_identifiers": CompanyIdentifiers(nse_symbol="GENSOL"),
        "publication_time": "2025-04-15",
        "coverage_note": (
            "SEBI interim order WTM/AB/CFID/CFID-SEC1/31379/2025-26 re Gensol Engg Ltd"
        ),
        "licence_status": "public_no_explicit_licence",
        "redistribution_allowed": "unclear",
        "terms_url": "https://www.sebi.gov.in/sebiweb/other/OtherAction.do?doTermsOfUse=yes",
    },
    {
        "source_id": "sebi",
        "source_url": "https://www.sebi.gov.in/enforcement/orders/apr-2025/interim-order-in-the-matter-of-gensol-engineering-limited_93458.html",
        "retrieval_url": "https://www.sebi.gov.in/sebi_data/attachdocs/jul-2025/confirm_order_gensol_engg.pdf",
        "document_type": "sebi_confirmatory_order",
        "company_identifiers": CompanyIdentifiers(nse_symbol="GENSOL"),
        "publication_time": "2025-07-30",
        "coverage_note": (
            "SEBI confirmatory order following the Apr 2025 interim order re Gensol Engg Ltd"
        ),
        "licence_status": "public_no_explicit_licence",
        "redistribution_allowed": "unclear",
        "terms_url": "https://www.sebi.gov.in/sebiweb/other/OtherAction.do?doTermsOfUse=yes",
    },
    {
        "source_id": "ibbi",
        "source_url": "https://ibbi.gov.in/orders/nclt?title=Dewan+Housing",
        "retrieval_url": "https://ibbi.gov.in/uploads/order/6c090481fbfc1830f8ef051502887749.pdf",
        "document_type": "nclt_order",
        "company_identifiers": CompanyIdentifiers(bse_scrip_code="511072"),
        "publication_time": None,
        "coverage_note": (
            "NCLT order re Dewan Housing Finance Corporation Ltd CIRP "
            "(CIRP admitted on an RBI petition, 3 Dec 2019 per public reporting; "
            "exact order date not machine-extracted from the PDF in Phase 0)"
        ),
        "licence_status": "public_no_explicit_licence",
        "redistribution_allowed": "unclear",
        "terms_url": None,
        "known_limitations": "Order date/number not OCR'd in Phase 0; content not parsed.",
    },
    {
        "source_id": "ibbi",
        "source_url": "https://ibbi.gov.in/orders/nclt?title=Jet+Airways",
        "retrieval_url": (
            "https://ibbi.gov.in/webadmin/pdf/order/2019/Jul/"
            "5th%20July%202019%20in%20the%20matter%20of%20Jet%20Airways%20"
            "(India)%20Ltd.%20C.P.%20(IB)-2205(MB)-2019_2019-07-16%2011:37:58.pdf"
        ),
        "document_type": "nclt_order",
        "company_identifiers": CompanyIdentifiers(nse_symbol="JETAIRWAYS"),
        "publication_time": "2019-07-05",
        "coverage_note": (
            "NCLT order, C.P. (IB)-2205(MB)-2019, re Jet Airways (India) Ltd CIRP "
            "(NCLT admitted the CIRP petition 20 June 2019 per public reporting; "
            "this is a subsequent order in the same case)"
        ),
        "licence_status": "public_no_explicit_licence",
        "redistribution_allowed": "unclear",
        "terms_url": None,
    },
    {
        "source_id": "ibbi",
        "source_url": "https://ibbi.gov.in/orders/nclt?title=Reliance+Capital",
        "retrieval_url": "https://ibbi.gov.in/orders/nclt?title=Reliance+Capital",
        "document_type": "nclt_order_listing_page",
        "company_identifiers": CompanyIdentifiers(bse_scrip_code="500111"),
        "publication_time": None,
        "coverage_note": (
            "IBBI order-listing page confirming case CP (IB) No. 1231/MB/2021 for "
            "Reliance Capital Ltd; the original Dec 2021 admission order itself was "
            "not individually isolated within the Phase 0 research budget (gap)."
        ),
        "licence_status": "public_no_explicit_licence",
        "redistribution_allowed": "unclear",
        "terms_url": None,
        "known_limitations": "This is the search/listing page, not the original admission order.",
    },
    {
        "source_id": "ibbi",
        "source_url": "https://ibbi.gov.in/orders/nclt?title=Future+Retail",
        "retrieval_url": "https://ibbi.gov.in/orders/nclt?title=Future+Retail",
        "document_type": "nclt_order_listing_page",
        "company_identifiers": CompanyIdentifiers(bse_scrip_code="540064"),
        "publication_time": None,
        "coverage_note": (
            "IBBI order-listing page confirming case C.P. (IB)-527(MB)-2022 for "
            "Future Retail Ltd; the original 20 Jul 2022 admission order itself was "
            "not individually isolated within the Phase 0 research budget (gap)."
        ),
        "licence_status": "public_no_explicit_licence",
        "redistribution_allowed": "unclear",
        "terms_url": None,
        "known_limitations": "This is the search/listing page, not the original admission order.",
    },
    {
        "source_id": "care",
        "source_url": "https://www.careratings.com/",
        "retrieval_url": (
            "https://www.careratings.com/upload/CompanyFiles/PR/"
            "Dewan%20Housing%20Finance%20Corporation%20Ltd.-06-05-2019.pdf"
        ),
        "document_type": "rating_rationale",
        "company_identifiers": CompanyIdentifiers(bse_scrip_code="511072"),
        "publication_time": "2019-06-05",
        "coverage_note": "CARE Ratings press release/rationale downgrading DHFL instruments",
        "licence_status": "public_no_explicit_licence",
        "redistribution_allowed": "unclear",
        "terms_url": "https://www.careratings.com/terms-condition",
    },
]


def main() -> int:
    settings = load_settings()
    manifest_path = settings.data_dir / "manifests" / "seed.jsonl"

    results = {"fetched": 0, "skipped_duplicate": 0, "blocked": 0, "errors": 0}

    with PoliteFetcher(
        contact_email=settings.contact_email,
        data_dir=settings.data_dir,
        manifest_path=manifest_path,
        rate_limit_seconds=settings.fetch_rate_limit_seconds,
        timeout_seconds=settings.fetch_timeout_seconds,
        max_retries=settings.fetch_max_retries,
        max_file_size_bytes=settings.fetch_max_file_size_bytes,
    ) as fetcher:
        for item in SEED_ITEMS:
            label = f"{item['source_id']}: {item['retrieval_url']}"
            try:
                entry = fetcher.fetch(**item)
                if entry is None:
                    print(f"SKIP (robots): {label}")
                    results["blocked"] += 1
                    continue
                if entry.skipped_duplicate_of:
                    print(f"DUPLICATE (already have content): {label}")
                    results["skipped_duplicate"] += 1
                else:
                    print(f"OK ({entry.bytes} bytes, sha256={entry.sha256[:12]}...): {label}")
                    results["fetched"] += 1
            except RobotsDisallowed:
                print(f"BLOCKED (robots.txt disallow): {label}")
                results["blocked"] += 1
            except LoginRedirectError as exc:
                print(f"BLOCKED (redirected to login-like URL {exc}): {label}")
                results["blocked"] += 1
            except FileTooLargeError as exc:
                print(f"BLOCKED (size guard: {exc}): {label}")
                results["blocked"] += 1
            except Exception as exc:  # noqa: BLE001
                print(f"ERROR ({exc.__class__.__name__}: {exc}): {label}")
                results["errors"] += 1

    print("---")
    print(f"Summary: {results}")
    return 0 if results["errors"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
