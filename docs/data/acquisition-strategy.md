# Restricted-Data Strategy

For every source not marked `AVAILABLE` in `docs/data/source-inventory.md`:
what would be needed to use it, indicative cost (only where publicly
stated), the best legitimate fallback, and the impact on later phases if
it is never obtained.

## BSE — BLOCKED

- **What would be needed**: Either (a) a documented, officially-sanctioned
  API/bulk-data agreement with BSE (none was found to exist publicly in
  Phase 0 — UNCLEAR whether one exists), or (b) accepting that a *human*
  using an ordinary browser can reach the same pages our tool cannot, which
  only helps if a human is doing the downloading, not an automated pipeline.
- **Indicative cost**: Not publicly stated; UNCLEAR.
- **Best legitimate fallback**: Company investor-relations sites. **Tried
  in Correction 1**: several seed/control companies' own sites (Vakrangee,
  Jet Airways, Brightcom, + 7 controls) were reachable and yielded real
  documents — see `docs/data/source-inventory.md` §"Company
  investor-relations sites". Not every company has a reachable or
  complete IR site (DHFL's own robots.txt disallows all crawling; Reliance
  Capital's and Gensol's sites were unreachable), so this fallback is
  partial, not complete.
- **Impact if never obtained**: Pledge/shareholding disclosures, XBRL
  results, and most governance-event announcements (auditor resignations,
  KMP/ID exits, forensic audit disclosures) for companies whose IR site is
  unreachable or incomplete have no other confirmed primary source in this
  inventory. Reduced from "the single largest open risk" (Phase 0) to "a
  per-company risk" (Correction 1) now that IR sites have proven to work
  for several companies.

## NSE (`www.nseindia.com`, `nsearchives.nseindia.com`) — BLOCKED

- **What would be needed**: Same as BSE for announcements/filings. NSE
  additionally blocks even a browser-identified request to
  `www.nseindia.com` itself (not just our tool), which suggests broader
  behavioural/IP-based controls, not purely a User-Agent filter.
- **Correction 1 resolved the price-data piece specifically**: a third NSE
  subdomain, `archives.nseindia.com`, is reachable with our honest UA and
  serves real bhavcopy files (see `docs/data/source-inventory.md`). This
  does **not** resolve announcements/shareholding/XBRL, which still have
  no confirmed NSE-side source.
- **Indicative cost**: UNCLEAR for the still-blocked pieces.
- **Best legitimate fallback**: Company IR sites (same as BSE) for
  non-price content; `archives.nseindia.com` directly for price data.
- **Impact if never obtained**: Announcement/XBRL/shareholding content
  still has the same risk profile as BSE above. Price-data risk is now
  largely closed.

## CRISIL Ratings — BLOCKED (judgment call, not a technical block)

- **What would be needed**: A decision from the user on whether to
  disregard CRISIL's AI-crawler-targeted robots.txt directives, given our
  tool's User-Agent is not literally one of the named bots. **This is a
  decision needing your approval** — see below.
- **Indicative cost**: None (no paywall observed).
- **Best legitimate fallback**: CARE/India Ratings/Acuité cover overlapping
  issuers for rating-action purposes.
- **Impact if never obtained**: Reduced rating-rationale coverage for
  issuers rated only by CRISIL; partially mitigated by other agencies.

## ICRA — BLOCKED

- **What would be needed**: Bypassing an active bot-fingerprinting
  challenge, which the ground rules explicitly prohibit.
- **Indicative cost**: UNCLEAR (no paywall observed — the block is
  anti-automation, not a paid tier).
- **Best legitimate fallback**: Same as CRISIL — other rating agencies.
- **Impact if never obtained**: Same as CRISIL.

## MCA (mca.gov.in) — BLOCKED (edge WAF); data.gov.in bulk mirror UNCLEAR

- **What would be needed**: mca.gov.in itself blocks every request
  regardless of User-Agent (edge WAF). The reported free bulk "Company
  Master Data" ZIP on `data.gov.in` was not independently fetched/verified
  in Phase 0 and should be tried first in Phase 1 before concluding MCA
  data is unobtainable. Certified document downloads (incorporation
  papers, filed financials) reportedly need a free MCA21 account.
- **Indicative cost**: Per secondary sources (not verified against a live
  MCA fee page): roughly Rs 25 per MOA/AOA/annual-return document, Rs 50
  for a Certificate of Incorporation, ~Rs 100 for filed financials —
  **UNVERIFIED, treat as indicative only**.
- **Best legitimate fallback**: the `data.gov.in` bulk mirror, if it checks
  out in Phase 1.
- **Impact if never obtained**: DIN/CIN master-data linking (company ↔
  director identity resolution) would need another source; this mostly
  affects entity-resolution quality, not core red-flag detection.

## India Ratings / Acuité — AVAILABLE_WITH_LIMITS

- **What would be needed**: Nothing beyond what Phase 1 would normally do
  — locate each company's rationale page and verify the terms-of-use text
  (neither was reviewed in Phase 0; both are a quick Phase 1 task, not a
  blocker).
- **Indicative cost**: None observed.
- **Best legitimate fallback**: n/a — these are themselves the fallback for
  CRISIL/ICRA.
- **Impact if never obtained**: Minor — CARE alone already demonstrated
  feasible.

## Infomerics / Brickwork Ratings — UNCLEAR

- **What would be needed**: Terms-of-use review (not done in Phase 0).
  Brickwork specifically: re-verify its current SEBI registration status
  live before relying on it (it had a registration disruption 2022-2024;
  see `sources.yaml`).
- **Indicative cost**: None observed.
- **Best legitimate fallback**: CARE/India Ratings/Acuité.
- **Impact if never obtained**: Minor — smaller agencies, narrower issuer
  coverage.

## Price data (Correction 1: largely resolved)

- **Primary path, now working**: `archives.nseindia.com` (see NSE section
  above) — real NSE equity bhavcopy, no account, no licence negotiation.
  A 210-file sample (Jan 2017 - Sep 2025) was downloaded in Correction 1.
- **Alpha Vantage — AWAITING_KEY**: free tier is very limited (25
  req/day), reportedly BSE-only (NSE discontinued) per public docs not
  independently re-verified, and requires creating a free API key.
  `.env`/`.env.example` have no `PRICE_API_KEY` — checked via `grep`, no
  match — so per instructions this was not used and no account was
  created. Moot given `archives.nseindia.com` already works.
- **Kaggle NSE/BSE datasets — REQUIRES_REGISTRATION**: several carry a
  CC0 licence per their publisher's own tag (e.g. "NSE India Stock Data
  1990-2021"), but downloading requires a Kaggle account, which ground
  rules forbid creating. Not used.
- **Indicative cost**: None for any of the above (Alpha Vantage free tier,
  Kaggle, and `archives.nseindia.com` are all free).
- **Impact if never using Alpha Vantage/Kaggle**: None identified — the
  working `archives.nseindia.com` path covers the Phase 0 seed windows
  already. Alpha Vantage/Kaggle remain documented options if BSE-specific
  or pre-2016 coverage is needed later and `archives.nseindia.com` cannot
  supply it.

## Commercial datasets (CMIE Prowess, Capitaline, ACE Equity, LSEG, Bloomberg) — REQUIRES_PAYMENT_OR_LICENCE

- **What would be needed**: An institutional subscription/licence for
  whichever vendor(s) are chosen; none was contacted or evaluated in Phase
  0 per instructions (alternatives only).
- **Indicative cost**: Not publicly stated for any of these (typically
  negotiated institutional pricing) — UNCLEAR.
- **Best legitimate fallback**: The free/public sources in this inventory,
  to the extent they prove sufficient.
- **Impact if never obtained**: These are redundancy/quality upgrades over
  free sources, not strictly required if the free-source gaps above
  (BSE/NSE, price data) get resolved another way.

## Academic datasets — UNCLEAR

- **What would be needed**: A Phase 1 (or follow-up Phase 0) literature
  search specifically for an Indian-corporate-governance/fraud/default
  dataset with an explicit, checkable licence. None was found within the
  Phase 0 time budget — this is an incomplete search, not a negative
  result.
- **Indicative cost**: Likely free if found (academic datasets are
  typically released under an open licence when released at all).
- **Best legitimate fallback**: n/a.
- **Impact if never obtained**: Would have been a nice-to-have for model
  validation/benchmarking; not a blocker for the core pipeline.

## Decisions needing your approval

1. **CRISIL**: disregard its AI-crawler-targeted robots.txt directives
   (our literal UA string isn't named, but the evident intent is clear),
   or treat it as BLOCKED like ICRA. Phase 0 defaulted to treating it as
   BLOCKED pending your decision. **Unchanged in Correction 1.**
2. **BSE/NSE announcements/shareholding/XBRL** (not price data, which is
   now resolved via `archives.nseindia.com`): whether to pursue an
   official data-licensing conversation with either exchange (a
   business/legal step, not an engineering task) rather than relying
   solely on company IR sites, which Correction 1 showed work for some
   companies but not all (DHFL's own robots.txt disallows crawling;
   Reliance Capital's and Gensol's IR sites were unreachable).
3. **Object storage for Phase 1+**: Correction 1 replaced MinIO (unpatched
   CVE-2026-40344) with Garage for the local dev stack — see
   `docs/adr/0003-object-storage.md`. This resolves the Phase 0 health
   check; it is still a decision for you whether Phase 1+ keeps Garage,
   uses a managed cloud object store, or something else.
4. **Manual-download checklist** (`docs/data/manual-download-checklist.md`,
   14 items): whether you want to retrieve any of these yourself via
   `data/inbox/` + `scripts/import_local.py`, now that the list is small
   and specific rather than "most of BSE/NSE."
