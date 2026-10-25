# Phase 0 Seed Universe

Starting candidate list is §8A of the Phase 0 brief. This document records,
for each candidate, what was actually verified against a primary source
**and legitimately downloaded**, what was confirmed only via secondary
reporting, and what was dropped — with reasons in every case. Events are
described neutrally, as disclosed; nothing here is a finding of wrongdoing.

**Correction 1 (2026-10-25)** added: three company-IR-site documents
(Vakrangee, Jet Airways, Brightcom), a SEBI-hosted document for CG Power,
a 7-company control group, and a 210-item NSE equity bhavcopy series
(twice-monthly, Jan 2017 - Sep 2025) from the newly-discovered
`archives.nseindia.com` path — see `docs/data/source-inventory.md`. Manpasand
Beverages remains dropped (no primary source found even after the retest —
see `docs/data/manual-download-checklist.md`).

## Kept — downloaded and hash-verified (see `data/manifests/seed.jsonl`)

### Gensol Engineering Ltd — SEBI interim order, 2025
- Primary source opened: `https://www.sebi.gov.in/enforcement/orders/apr-2025/interim-order-in-the-matter-of-gensol-engineering-limited_93458.html`
  (order WTM/AB/CFID/CFID-SEC1/31379/2025-26, dated 15 Apr 2025).
- Downloaded: the interim order PDF and the subsequent (Jul 2025)
  confirmatory order PDF, both linked directly from that page.
- Event, as disclosed: SEBI's interim order restrained the company's
  promoter-directors from securities-market activity and KMP/director roles
  pending further proceedings, and directed a forensic audit, per the
  order text.

### Dewan Housing Finance Corporation Ltd (DHFL) — CIRP admission, 2019
- Primary source opened: `https://ibbi.gov.in/orders/nclt?title=Dewan+Housing`
  (case listing), and a specific NCLT order PDF at
  `https://ibbi.gov.in/uploads/order/6c090481fbfc1830f8ef051502887749.pdf`.
- Also downloaded: a CARE Ratings (CareEdge) rationale dated 2019-06-05
  downgrading DHFL instruments, from
  `https://www.careratings.com/upload/CompanyFiles/PR/Dewan%20Housing%20Finance%20Corporation%20Ltd.-06-05-2019.pdf`.
- Event, as disclosed: per public reporting of the NCLT record, CIRP was
  admitted on an RBI petition with effect from 3 Dec 2019. Phase 0 did not
  OCR/parse the downloaded order PDF to independently re-derive this date
  from its text — the date above is from secondary reporting, flagged as
  such, not re-verified against the PDF's own content.

### Jet Airways (India) Ltd — CIRP admission, 2019
- Primary source opened: `https://ibbi.gov.in/orders/nclt?title=Jet+Airways`,
  and an NCLT order PDF (case C.P. (IB)-2205(MB)-2019, dated 5 Jul 2019) at
  `https://ibbi.gov.in/webadmin/pdf/order/2019/Jul/5th%20July%202019%20in%20the%20matter%20of%20Jet%20Airways...pdf`.
- Event, as disclosed: per public reporting, NCLT admitted the CIRP
  petition on 20 Jun 2019; the downloaded PDF is a subsequent order in the
  same case (dated 5 Jul 2019), confirmed reachable and hash-verified, not
  the original admission order itself.

### Vakrangee Ltd — statutory auditor resignation, 2018 (Correction 1)
- Primary source opened: `https://www.vakrangee.in/pdf/news_announcements.html`,
  the company's own News & Announcements archive.
- **First download attempt failed, diagnosed, and fixed within Phase 0**:
  all three documents initially errored with
  `CERTIFICATE_VERIFY_FAILED: unable to get local issuer certificate` —
  `vakrangee.in`'s server does not send a complete TLS certificate chain.
  `curl` (via Windows schannel, which opportunistically fetches missing
  intermediates) succeeded anyway, while httpx's certifi-bundle verifier
  correctly refused the incomplete chain. The fetcher now verifies TLS via
  `truststore` (the OS trust store) instead of a static bundle — still
  full certificate verification, just with the same chain-completion
  behaviour a browser has — see the ADR 0002 addendum. Disabling
  verification outright was considered and rejected.
- Downloaded (after the fix, re-run and confirmed): the actual Price
  Waterhouse & Co resignation letter (`ResignLetter.pdf`, 250,640 bytes),
  the company's own update on the resignation (512,753 bytes), and its
  Reg 30 SEBI LODR intimation to the exchange (237,412 bytes) — all three
  hash-verified in `data/manifests/seed.jsonl`.
- Event, as disclosed: Price Waterhouse & Co resigned as statutory auditor
  on 27 Apr 2018, citing undelivered information requested for the audit
  of the year ended 31 Mar 2018 (per the letter's own stated reason).

### Jet Airways (India) Ltd — shareholding pattern (Correction 1)
- Downloaded directly from `jetairways.com`: the shareholding pattern as
  of 31 Mar 2022 (`SHP_31032022.pdf`). This supplements the IBBI NCLT
  order already in the seed; it is a post-CIRP pattern, not a pre-event
  one — the pre-event (2018-2019) pattern was not found on the company's
  own site and is listed as a gap in
  `docs/data/manual-download-checklist.md`.

### Brightcom Group Ltd — annual report (Correction 1)
- Downloaded directly from `brightcomgroup.com`: the FY2018-19 annual
  report PDF. The SEBI interim-order primary source itself (Apr 2023) was
  still not located within budget — see the "confirmed via secondary
  reporting only" entry below, unchanged from the original Phase 0 pass.

### CG Power and Industrial Solutions Ltd — SEBI-hosted document (Correction 1)
- Downloaded: `https://www.sebi.gov.in/sebi_data/attachdocs/sep-2019/1568728579007.pdf`,
  a SEBI-hosted document from September 2019 found via search in connection
  with CG Power's board-disclosed forensic investigation into irregularities.
- Known limitation: this document was found via a general web search, not
  via SEBI's own enforcement-orders listing, and its exact nature (order,
  circular, or other) was not reviewed/classified in Phase 0 — recorded
  honestly as a gap rather than asserting what it is.
- CG Power's own site (`cgglobal.com`) did not surface the original Aug
  2019 BSE disclosure of unauthorised transactions within budget — listed
  in `docs/data/manual-download-checklist.md`.

## Control group (Correction 1)

**Selection rule**: for each event company's sector (housing finance,
aviation, retail, power equipment, renewables, and — loosely, for
Vakrangee's tech-enabled retail/kiosk model — IT services), pick a
comparably-sized listed company with (a) a live, reachable investor-
relations site and (b) no SEBI order, IBBI admission, auditor resignation,
or comparable governance event found in Phase 0's research for that
company. None of the seven below had any such event surface during this
project's research; absence-of-evidence is not treated as proof of
absence, and no exchange-announcement search (BLOCKED, see
source-inventory.md) was done to actively rule out a smaller, less-
publicised event.

| Control | Sector (vs.) | Document downloaded | Source |
|---|---|---|---|
| LIC Housing Finance Ltd | Housing finance (vs. DHFL) | Shareholding pattern, Jul 2025 | `cdn.lichousing.com` |
| PNB Housing Finance Ltd | Housing finance (vs. DHFL) | IR shareholding-pattern page | `pnbhousing.com` |
| SpiceJet Ltd | Aviation (vs. Jet Airways) | Shareholding pattern Q3 FY24-25 | `corporate.spicejet.com` |
| Avenue Supermarts Ltd (DMart) | Retail (vs. Future Retail) | Investor presentation, Mar 2024 | `api.dmartindia.com` |
| Thermax Ltd | Power equipment (vs. CG Power) | 44th Annual Report | `thermaxglobal.com` |
| Suzlon Energy Ltd | Renewables (vs. Gensol) | IR shareholder-information page | `suzlon.com` |
| Mastek Ltd | IT services (vs. Vakrangee) | Shareholding pattern Q1 FY17-18 | `mastek.com` |

Note: IndiGo (`goindigo.in`) was the first aviation-control candidate
tried; it was unreachable (connection failure) on retest, so SpiceJet was
substituted.

## Kept — case confirmed, but only as a listing page (document gap)

### Reliance Capital Ltd — CIRP admission, late 2021
- Primary source opened and downloaded (as HTML):
  `https://ibbi.gov.in/orders/nclt?title=Reliance+Capital`, confirming case
  CP (IB) No. 1231/MB/2021.
- Gap: the original Dec 2021 admission order PDF itself was not
  individually isolated from the (paginated) order list within the Phase 0
  research budget. Only the listing page is in the seed manifest.

### Future Retail Ltd — CIRP admission, 2022
- Primary source opened and downloaded (as HTML):
  `https://ibbi.gov.in/orders/nclt?title=Future+Retail`, confirming case
  C.P. (IB)-527(MB)-2022.
- Gap: same as Reliance Capital — the original admission order PDF was not
  individually isolated within budget.

## Confirmed via secondary reporting only — not downloaded (gap)

### Brightcom Group Ltd — SEBI interim order, 2023
- SEBI issued a show-cause-notice-cum-interim order dated 13 Apr 2023
  (order WTM/ASB/CFID/CFID_4/25730/2023-24) and a further interim order on
  22 Aug 2023, per multiple secondary reports (Business Standard, Zee
  Business, Moneylife — see `sources.yaml` note if later added).
- Gap: the exact `sebi.gov.in/enforcement/orders/...` page/PDF URL was not
  located within the Phase 0 research budget (SEBI's own order-search UI
  was not explored deeply enough to find it). **Dropped from the downloaded
  seed set**; kept here only as a documented gap, not cited as a primary
  source.

### Manpasand Beverages Ltd — statutory auditor resignation, 2019
- Deloitte Haskins & Sells resigned as statutory auditor in May 2018 (and
  a successor auditor, Mehra Goel & Co, resigned in turn in Jul 2019), per
  well-documented news reporting. Manpasand's own site
  (`manpasand.co.in`) was retested in Correction 1 — robots.txt is
  reachable and non-blocking, but no announcements/news archive page
  analogous to Vakrangee's was located within budget, and
  no alternative primary source was found. **Still dropped** — listed in
  `docs/data/manual-download-checklist.md` for manual retrieval from
  BSE.

## Price data (Correction 1)

A 210-item twice-monthly NSE equity bhavcopy series (Jan 2017 - Sep 2025,
union of all event-company windows) was downloaded from
`archives.nseindia.com` — see `docs/data/source-inventory.md` for how this
host was found and verified. **Survivorship check**: DHFL (suspended/CIRP
from Dec 2019), Jet Airways (CIRP from mid-2019, later delisted), Reliance
Capital (CIRP from Dec 2021) and Future Retail (CIRP from Jul 2022, later
delisted) all have bhavcopy snapshots dated *after* their respective
events in this series — the exact per-symbol row-presence check (did that
ticker's row still exist in each file) was not individually parsed in
Phase 0; the files themselves are real and present for those dates, which
is the file-level survivorship evidence this phase can make. Row-level
parsing is Phase 1 work. `Alpha Vantage` and `Kaggle` were evaluated and
not used — see `docs/data/acquisition-strategy.md`.

## Window

Each individual document above carries its own real `publication_time`
(or `null` where not stated) in `data/manifests/seed.jsonl`. The bhavcopy
series' window is Jan 2017 - Sep 2025, chosen as the union of all event
companies' ~24-months-before to ~6-months-after windows (DHFL/Jet Airways
on the early end, Gensol on the late end).
