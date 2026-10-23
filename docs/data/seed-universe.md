# Phase 0 Seed Universe

Starting candidate list is §8A of the Phase 0 brief. This document records,
for each candidate, what was actually verified against a primary source
**and legitimately downloaded**, what was confirmed only via secondary
reporting, and what was dropped — with reasons in every case. Events are
described neutrally, as disclosed; nothing here is a finding of wrongdoing.

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

### Vakrangee Ltd — statutory auditor resignation, 2018
### Manpasand Beverages Ltd — statutory auditor resignation, 2019
### CG Power and Industrial Solutions Ltd — board-disclosed investigation, 2019
- All three events are well-documented in public reporting, but their
  primary disclosures are BSE/NSE corporate-announcement filings, and both
  exchanges are marked **BLOCKED** for this project's acquisition tool (see
  `docs/data/source-inventory.md`). No company-IR-site or alternative
  primary source was located and verified for these three within the Phase
  0 budget. **Dropped** — no primary-source URL was opened for any of these
  three, so none is included in the seed manifest or cited as verified.

## Control group

**Not completed.** The task asked for 6-8 comparable listed companies (same
sectors: housing finance, aviation, retail, IT services, power equipment,
renewables) with no comparable disclosed event in the matching window, each
selection reason citing a URL actually opened. Building a credible "nothing
happened" control set requires searching exchange announcement archives
(BSE/NSE) to confirm the *absence* of a comparable event — exactly the
sources that are BLOCKED for this tool. Given the time budget remaining
after the primary-event research above, no control company was selected or
verified. **This is an open gap**, not a silent omission — see
`docs/data/feasibility-assessment.md` for its downstream impact (Phase
2+ needs a non-BSE/NSE way to confirm "no event" for controls, e.g. company
IR sites or a licensed data vendor).

## Price data

**Not attempted.** With BSE and NSE bhavcopy archives both BLOCKED for an
honestly-identified client, no price history was downloaded for the seed
window. The survivorship-bias question ("are rows for delisted/suspended
companies still present?") therefore could not be tested empirically in
Phase 0 — see `docs/data/feasibility-assessment.md`.

## Window

Not applicable in the usual sense, since no bulk date-range archive was
downloaded. Each individual document above carries its own real
`publication_time` (or `null` where not stated) in
`data/manifests/seed.jsonl`.
