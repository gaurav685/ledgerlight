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
- **Best legitimate fallback**: Company investor-relations sites often
  mirror the same announcements/annual reports BSE hosts, under different
  (and likely less aggressive) bot-mitigation — untested in Phase 0, but
  the most promising lead.
- **Impact if never obtained**: Pledge/shareholding disclosures, XBRL
  results, and most governance-event announcements (auditor resignations,
  KMP/ID exits, forensic audit disclosures) have no other confirmed
  primary source in this inventory. This is the single largest open risk
  to the whole project.

## NSE — BLOCKED

- **What would be needed**: Same as BSE. NSE additionally blocks even a
  browser-identified request to `www.nseindia.com` itself (not just our
  tool), which suggests broader behavioural/IP-based controls, not purely
  a User-Agent filter.
- **Indicative cost**: UNCLEAR.
- **Best legitimate fallback**: Same as BSE — company IR sites, untested.
- **Impact if never obtained**: Same as BSE; NSE and BSE substantially
  overlap in disclosure content for dual-listed companies, so losing both
  is strictly worse than losing one.

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

## Price-data alternatives — UNCLEAR

- **What would be needed**: With BSE/NSE bhavcopy BLOCKED, Phase 1 needs to
  identify and verify a specific licensed alternative (none was researched
  in Phase 0 — this is a gap, not a conclusion that none exists).
- **Indicative cost**: Unknown until a specific vendor is evaluated.
- **Best legitimate fallback**: None identified yet.
- **Impact if never obtained**: No price-based labels (large drawdown,
  delisting detection via price history) and no price-based features for
  modelling at all. This is a significant open risk alongside the
  BSE/NSE announcement gap.

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
   BLOCKED pending your decision.
2. **BSE/NSE**: whether to pursue an official data-licensing conversation
   with either exchange (a business/legal step, not a Phase 1 engineering
   task) rather than relying on company IR sites as a technical fallback.
3. **MinIO image source**: MinIO's community edition was archived in Feb
   2026 and removed from both Docker Hub and quay.io. The only verified
   pullable image in Phase 0 was the community-maintained
   `bitnamilegacy/minio` mirror, which carries an unpatched CVE
   (CVE-2026-40344, auth bypass, CVSS 8.8) in the community edition with
   no fix available. This is fine for a local, loopback-only, no-real-data
   Phase 0 health check, but **Phase 1+ should not inherit this choice
   without a deliberate decision** — alternatives include MinIO AIStor
   (commercial), a different self-hosted S3-compatible store, or a managed
   cloud object store.
4. **Price data**: whether to scope a specific licensed vendor now, or
   defer until the BSE/NSE access question (decision 2) is resolved, since
   a successful exchange relationship might make a separate price vendor
   unnecessary.
