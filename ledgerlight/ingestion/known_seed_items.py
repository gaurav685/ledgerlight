"""The canonical list of individually-verified Phase 0/Correction-1
documents, fetched by both scripts/acquire_seed.py (the original Phase 0
entrypoint) and the Phase 1 per-source ingestion jobs (ledgerlight.ingestion
.sebi / .ibbi / .care / .company_ir), each filtering by source_id. Moved
here in Phase 1 so there is exactly one list, not two drifting copies —
see docs/adr/0004-metadata-store-and-orchestration.md.
"""

from __future__ import annotations

from typing import Any

from ledgerlight.acquisition.manifest import CompanyIdentifiers

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
    # --- Correction 1: documents obtained directly from company IR sites ---
    # (Regulation 46 of SEBI LODR requires listed entities to publish annual
    # reports, results, shareholding patterns and credit ratings on their own
    # website — see docs/data/source-inventory.md §B2.)
    {
        "source_id": "vakrangee_ir",
        "source_url": "https://www.vakrangee.in/pdf/news_announcements.html",
        "retrieval_url": "https://www.vakrangee.in/pdf/News_and_Announcements/ResignLetter.pdf",
        "document_type": "auditor_resignation_letter",
        "company_identifiers": CompanyIdentifiers(nse_symbol="VAKRANGEE"),
        "publication_time": "2018-04-27",
        "coverage_note": (
            "Price Waterhouse & Co resignation letter as statutory auditor, "
            "from Vakrangee's own IR site"
        ),
        "licence_status": "public_no_explicit_licence",
        "redistribution_allowed": "unclear",
        "terms_url": None,
    },
    {
        "source_id": "vakrangee_ir",
        "source_url": "https://www.vakrangee.in/pdf/news_announcements.html",
        "retrieval_url": (
            "https://www.vakrangee.in/pdf/News_and_Announcements/"
            "36Company%20Update%20on%20Resignation%20of%20Statutory%20Auditors.pdf"
        ),
        "document_type": "auditor_resignation_company_update",
        "company_identifiers": CompanyIdentifiers(nse_symbol="VAKRANGEE"),
        "publication_time": "2018",
        "coverage_note": "Vakrangee's own company update on the 2018 statutory auditor resignation",
        "licence_status": "public_no_explicit_licence",
        "redistribution_allowed": "unclear",
        "terms_url": None,
    },
    {
        "source_id": "vakrangee_ir",
        "source_url": "https://www.vakrangee.in/pdf/news_announcements.html",
        "retrieval_url": (
            "https://www.vakrangee.in/pdf/News_and_Announcements/"
            "37Intimation%20to%20Stock%20Exchange%20regarding%20resignation%20of%20"
            "Statutory%20Auditors%20%E2%80%93%20Reg.%2030%20SEBI%20LODR%20Regulations.pdf"
        ),
        "document_type": "reg30_intimation",
        "company_identifiers": CompanyIdentifiers(nse_symbol="VAKRANGEE"),
        "publication_time": "2018",
        "coverage_note": (
            "Vakrangee's Reg 30 SEBI LODR intimation to the exchange re auditor resignation"
        ),
        "licence_status": "public_no_explicit_licence",
        "redistribution_allowed": "unclear",
        "terms_url": None,
    },
    {
        "source_id": "jetairways_ir",
        "source_url": "https://www.jetairways.com/",
        "retrieval_url": "https://www.jetairways.com/information/Documents/SHP_31032022.pdf",
        "document_type": "shareholding_pattern",
        "company_identifiers": CompanyIdentifiers(nse_symbol="JETAIRWAYS", bse_scrip_code="532617"),
        "publication_time": "2022-03-31",
        "coverage_note": (
            "Jet Airways shareholding pattern as of 31 Mar 2022, from the company's own site"
        ),
        "licence_status": "public_no_explicit_licence",
        "redistribution_allowed": "unclear",
        "terms_url": None,
    },
    {
        "source_id": "brightcom_ir",
        "source_url": "https://www.brightcomgroup.com/",
        "retrieval_url": (
            "https://www.brightcomgroup.com/wp-content/uploads/2021/03/Annual-Report-2018-2019.pdf"
        ),
        "document_type": "annual_report",
        "company_identifiers": CompanyIdentifiers(nse_symbol="BCG", bse_scrip_code="532368"),
        "publication_time": "2019",
        "coverage_note": "Brightcom Group FY2018-19 annual report, from the company's own site",
        "licence_status": "public_no_explicit_licence",
        "redistribution_allowed": "unclear",
        "terms_url": None,
    },
    {
        "source_id": "sebi",
        "source_url": "https://www.sebi.gov.in/sebi_data/attachdocs/sep-2019/1568728579007.pdf",
        "retrieval_url": "https://www.sebi.gov.in/sebi_data/attachdocs/sep-2019/1568728579007.pdf",
        "document_type": "sebi_related_document",
        "company_identifiers": CompanyIdentifiers(nse_symbol="CGPOWER"),
        "publication_time": "2019-09",
        "coverage_note": (
            "SEBI-hosted document (Sep 2019) relevant to CG Power and Industrial "
            "Solutions Ltd's board-disclosed forensic investigation into irregularities; "
            "exact document type not machine-classified in Phase 0 (gap)."
        ),
        "licence_status": "public_no_explicit_licence",
        "redistribution_allowed": "unclear",
        "terms_url": "https://www.sebi.gov.in/website-policy.html",
        "known_limitations": (
            "Found via search, not SEBI's enforcement-orders listing; "
            "content not reviewed to confirm exact document type."
        ),
    },
    # --- Control group (docs/data/seed-universe.md documents the selection rule) ---
    {
        "source_id": "lichousing_ir",
        "source_url": "https://www.lichousing.com/investors/shareholding-pattern",
        "retrieval_url": "https://cdn.lichousing.com/2025/07/lichfl_shareholders_pattern_q125.pdf",
        "document_type": "shareholding_pattern",
        "company_identifiers": CompanyIdentifiers(nse_symbol="LICHSGFIN", bse_scrip_code="500253"),
        "publication_time": "2025-07",
        "coverage_note": (
            "Control (housing finance, vs. DHFL): LIC Housing Finance shareholding pattern"
        ),
        "licence_status": "public_no_explicit_licence",
        "redistribution_allowed": "unclear",
        "terms_url": None,
    },
    {
        "source_id": "pnbhousing_ir",
        "source_url": "https://www.pnbhousing.com/investors/shareholding-pattern",
        "retrieval_url": "https://www.pnbhousing.com/investors/shareholding-pattern",
        "document_type": "ir_page",
        "company_identifiers": CompanyIdentifiers(nse_symbol="PNBHOUSING"),
        "publication_time": None,
        "coverage_note": (
            "Control (housing finance, vs. DHFL): PNB Housing Finance IR shareholding page"
        ),
        "licence_status": "public_no_explicit_licence",
        "redistribution_allowed": "unclear",
        "terms_url": None,
    },
    {
        "source_id": "spicejet_ir",
        "source_url": "https://corporate.spicejet.com/investorsnotices.aspx",
        "retrieval_url": "https://corporate.spicejet.com/Content/pdf/ShareholdingPatternQ3_24_25.pdf",
        "document_type": "shareholding_pattern",
        "company_identifiers": CompanyIdentifiers(nse_symbol="SPICEJET"),
        "publication_time": "2024-12-31",
        "coverage_note": "Control (aviation, vs. Jet Airways): SpiceJet shareholding pattern",
        "licence_status": "public_no_explicit_licence",
        "redistribution_allowed": "unclear",
        "terms_url": None,
    },
    {
        "source_id": "dmart_ir",
        "source_url": "https://www.dmartindia.com/investor-relationship",
        "retrieval_url": (
            "https://api.dmartindia.com/corporate/content/file/v1/2/"
            "3uvHxSiASSCtZ94xNwxwjgea1714823973/"
            "Investor%20Presentation%20for%20the%20year%20ended%2031st%20March,%202024.pdf"
        ),
        "document_type": "investor_presentation",
        "company_identifiers": CompanyIdentifiers(nse_symbol="DMART", bse_scrip_code="540376"),
        "publication_time": "2024-03-31",
        "coverage_note": (
            "Control (retail, vs. Future Retail): Avenue Supermarts (DMart) investor presentation"
        ),
        "licence_status": "public_no_explicit_licence",
        "redistribution_allowed": "unclear",
        "terms_url": None,
    },
    {
        "source_id": "thermax_ir",
        "source_url": "https://www.thermaxglobal.com/investors/annual-reports",
        "retrieval_url": "https://www.thermaxglobal.com/sites/default/files/2026-04/Thermax_44-Annual-Report_0.pdf",
        "document_type": "annual_report",
        "company_identifiers": CompanyIdentifiers(nse_symbol="THERMAX", bse_scrip_code="500411"),
        "publication_time": "2025",
        "coverage_note": "Control (power equipment, vs. CG Power): Thermax 44th annual report",
        "licence_status": "public_no_explicit_licence",
        "redistribution_allowed": "unclear",
        "terms_url": None,
    },
    {
        "source_id": "suzlon_ir",
        "source_url": "https://www.suzlon.com/investors/shareholder-information/",
        "retrieval_url": "https://www.suzlon.com/investors/shareholder-information/",
        "document_type": "ir_page",
        "company_identifiers": CompanyIdentifiers(nse_symbol="SUZLON"),
        "publication_time": None,
        "coverage_note": "Control (renewables, vs. Gensol Engineering): Suzlon Energy IR page",
        "licence_status": "public_no_explicit_licence",
        "redistribution_allowed": "unclear",
        "terms_url": None,
    },
    {
        "source_id": "mastek_ir",
        "source_url": "https://www.mastek.com/",
        "retrieval_url": "https://www.mastek.com/wp-content/uploads/2022/08/Shareholding-Pattern-Q1-2017-18.pdf",
        "document_type": "shareholding_pattern",
        "company_identifiers": CompanyIdentifiers(nse_symbol="MASTEK", bse_scrip_code="523704"),
        "publication_time": "2017",
        "coverage_note": (
            "Control (IT services, vs. Vakrangee): Mastek shareholding pattern Q1 2017-18"
        ),
        "licence_status": "public_no_explicit_licence",
        "redistribution_allowed": "unclear",
        "terms_url": None,
    },
]
