"""Phase 3 Sec3/Sec4 prerequisite: broaden IBBI discovery from the
15-company SEED-track universe to every currently-listed company, using
IBBI's real title search (ledgerlight.ingestion.ibbi) driven by real
legal company names -- not ticker symbols.

Why not ticker symbols: confirmed live (2026-10-30) that IBBI's title
search fails on a ticker alone for a real distress case ("RELCAPITAL"
-> 0 results) while the real legal name finds it ("Reliance Capital" ->
15 results), and a ticker can produce unrelated false-positive matches
for a healthy company ("TCS" -> 3 results, almost certainly an
unrelated acronym collision). The fix: NSE publishes a real, compliant
bulk symbol-to-legal-name master file on the same already-verified
archives.nseindia.com host used for bhavcopy --
/content/equities/EQUITY_L.csv (currently-listed equities) and
/content/equities/SME_EQUITY_L.csv (SME segment) -- fetched here via
the normal PoliteFetcher path, so it's a real, auditable, manifest-logged
fetch like every other source in this project, not a one-off curl.

Known, disclosed scope limit: these master files list only CURRENTLY
LISTED companies (2,621 + 5 real rows, 2026-10-30). Companies delisted
before today (voluntarily, via CIRP, or otherwise) are not in them, so
this run cannot check IBBI history for the ~1,900 companies in our
bootstrapped universe that are no longer listed, beyond the ones
already individually known (the 15 SEED-track companies). Their
bhavcopy disappearance is itself already a real signal (Sec3's
secondary outcome (c)); distinguishing a CIRP-driven disappearance from
a benign one (merger, buyback, voluntary delisting) for that remaining
~1,900-company gap is not attempted here, and is reported as a real,
disclosed limitation, not silently assumed either way.

Usage: python scripts/ibbi_universe_discovery.py
"""

from __future__ import annotations

import csv
import io
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from ledgerlight.acquisition.fetcher import PoliteFetcher  # noqa: E402
from ledgerlight.acquisition.manifest import CompanyIdentifiers  # noqa: E402
from ledgerlight.config.settings import load_settings  # noqa: E402
from ledgerlight.db.session import make_session_factory  # noqa: E402
from ledgerlight.ingestion.ibbi import run_ibbi_discovery_job  # noqa: E402
from ledgerlight.storage.s3_store import ObjectStore  # noqa: E402

MASTER_FILES = (
    "https://archives.nseindia.com/content/equities/EQUITY_L.csv",
    "https://archives.nseindia.com/content/equities/SME_EQUITY_L.csv",
)


def _parse_master_csv(csv_text: str) -> list[tuple[str, CompanyIdentifiers]]:
    reader = csv.DictReader(io.StringIO(csv_text))
    companies: list[tuple[str, CompanyIdentifiers]] = []
    for row in reader:
        # DictReader yields None (not '') for a short row's missing
        # trailing fields -- real, messy data, not hypothetical.
        row = {k.strip(): (v or "").strip() for k, v in row.items() if k}
        symbol = row.get("SYMBOL")
        name = row.get("NAME OF COMPANY")
        isin = row.get("ISIN NUMBER")
        if not symbol or not name:
            continue
        companies.append((name, CompanyIdentifiers(nse_symbol=symbol, isin=isin or None)))
    return companies


def main() -> int:
    settings = load_settings()
    store = ObjectStore(settings)
    session_factory = make_session_factory(settings)

    all_companies: list[tuple[str, CompanyIdentifiers]] = []
    with (
        session_factory() as session,
        PoliteFetcher(
            contact_email=settings.contact_email,
            data_dir=settings.data_dir,
            manifest_path=settings.data_dir / "manifests" / "live_ingestion.jsonl",
            rate_limit_seconds=settings.fetch_rate_limit_seconds,
            timeout_seconds=settings.fetch_timeout_seconds,
            max_retries=settings.fetch_max_retries,
            max_file_size_bytes=settings.fetch_max_file_size_bytes,
        ) as fetcher,
    ):
        for url in MASTER_FILES:
            entry = fetcher.fetch(
                source_id="nse_archives",
                source_url="https://archives.nseindia.com/",
                retrieval_url=url,
                document_type="equity_master_list",
                licence_status="public_no_explicit_licence",
                redistribution_allowed="unclear",
                coverage_note="NSE equity master list (symbol -> legal name -> ISIN), "
                "fetched to drive full-universe IBBI name-based discovery (Phase 3 Sec3)",
            )
            if entry is None:
                print(f"robots.txt disallowed: {url}")
                continue
            body = Path(entry.local_path).read_bytes()
            all_companies.extend(_parse_master_csv(body.decode("utf-8")))

        print(f"companies parsed from master files: {len(all_companies)}")
        deduped = {name: ids for name, ids in all_companies}
        companies = list(deduped.items())
        print(f"distinct company names: {len(companies)}")

        stats = run_ibbi_discovery_job(
            session, store, fetcher, settings.contact_email, seed_companies=companies
        )
    print(stats)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
