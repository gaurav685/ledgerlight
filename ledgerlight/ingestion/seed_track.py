"""The Phase 3 SEED-track company universe (docs/data/seed-universe.md):
the event companies plus the 7-company control group, individually
verified in Phase 0/1. Used by every per-company discovery job (CARE,
IBBI, ...) that drives a real search API/form from a known company list
rather than crawling blindly -- most of a listing/rating/order source
has nothing to do with any company this project tracks, and driving
discovery by name also directly produces the name->identifier link
later Phase 3 sections ask for.

search_name is the real legal/trading name used against each source's
own search box; identifiers mirror known_seed_items.py so Document rows
link to the same company identity across sources.

Dewan Housing Finance, Reliance Capital and Future Retail carry an
`nse_symbol` here (DHFL/RELCAPITAL/FRETAIL -- their real, historical NSE
tickers before CIRP/delisting), not just `bse_scrip_code`: a Phase 3
§2.4 investigation found `company_identifiers` has almost no BSE_CODE
rows at all (the company bootstrap is NSE-bhavcopy-only), so a
`bse_scrip_code`-only identifier never auto-links to a real `Company`
row for these three -- see `docs/phase-3/phase-3-report.md`'s §2.4
addendum and `scripts/migrate_company_dedup.py` for the real bug this
also surfaced and fixed (one `Company` row per ISIN instead of per real
company, fragmenting debt-heavy issuers like DHFL into dozens of rows).
"""

from __future__ import annotations

from ledgerlight.acquisition.manifest import CompanyIdentifiers

SEED_COMPANY_SEARCH_NAMES: list[tuple[str, CompanyIdentifiers]] = [
    ("Gensol Engineering", CompanyIdentifiers(nse_symbol="GENSOL")),
    ("Dewan Housing Finance", CompanyIdentifiers(nse_symbol="DHFL", bse_scrip_code="511072")),
    ("Jet Airways", CompanyIdentifiers(nse_symbol="JETAIRWAYS", bse_scrip_code="532617")),
    ("Vakrangee", CompanyIdentifiers(nse_symbol="VAKRANGEE")),
    ("Brightcom Group", CompanyIdentifiers(nse_symbol="BCG", bse_scrip_code="532368")),
    ("CG Power and Industrial Solutions", CompanyIdentifiers(nse_symbol="CGPOWER")),
    ("Reliance Capital", CompanyIdentifiers(nse_symbol="RELCAPITAL", bse_scrip_code="500111")),
    ("Future Retail", CompanyIdentifiers(nse_symbol="FRETAIL", bse_scrip_code="540064")),
    ("LIC Housing Finance", CompanyIdentifiers(nse_symbol="LICHSGFIN", bse_scrip_code="500253")),
    ("PNB Housing Finance", CompanyIdentifiers(nse_symbol="PNBHOUSING")),
    ("SpiceJet", CompanyIdentifiers(nse_symbol="SPICEJET")),
    ("Avenue Supermarts", CompanyIdentifiers(nse_symbol="DMART", bse_scrip_code="540376")),
    ("Thermax", CompanyIdentifiers(nse_symbol="THERMAX", bse_scrip_code="500411")),
    ("Suzlon Energy", CompanyIdentifiers(nse_symbol="SUZLON")),
    ("Mastek", CompanyIdentifiers(nse_symbol="MASTEK", bse_scrip_code="523704")),
]
