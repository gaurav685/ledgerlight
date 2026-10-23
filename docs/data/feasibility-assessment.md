# Phase 0 Feasibility Assessment

All figures below are estimates derived from something actually observed in
Phase 0 (a real document count, a real pagination depth, a real measured
fetch), explicitly labelled as such. Nothing here is a confirmed production
backfill plan — that is Phase 1+ work.

## Backfill estimate

Methodology: `time_hours ≈ N_documents × (rate_limit_seconds + avg_fetch_seconds) / 3600`,
using the project's default per-host rate limit (`LEDGERLIGHT_FETCH_RATE_LIMIT_SECONDS=2.0`)
and the average document size/fetch time actually observed in the Phase 0
seed run (7 documents, 3.1 MB total, well under a second of transfer time
each on a normal connection — the rate limit dominates, not download time).

### IBBI (AVAILABLE)

- **Observed sample**: while researching the Reliance Capital / Future
  Retail cases, a search result surfaced an IBBI order-listing URL
  `https://ibbi.gov.in/hi/orders/nclt?page=1685`, i.e. the *unfiltered*
  all-cases order listing has **at least 1,685 pages**. Our own fetch of a
  single filtered listing page (`?title=Reliance+Capital`) showed roughly
  14 order links per page.
- **Estimate**: 1,685 pages × ~14 orders/page ≈ **~23,600 order documents**
  (ESTIMATE — this counts *all* orders of *all* types across *all* cases
  seen by that pagination depth, not unique CIRP admissions; the unique
  number of distinct companies/cases is smaller and was not measured).
- **Time**: 23,600 × 2s ÷ 3600 ≈ **~13 hours** of pure rate-limited
  sequential fetching for the full all-time order corpus, at the default
  2-second per-host delay. Feasible within roughly one working day,
  single-threaded, against one host.
- Going back only to IBC's 2016 inception is implicit in "all orders" above
  (IBBI predates nothing earlier); no separate 2010-cutoff adjustment
  applies to this source.

### SEBI (AVAILABLE)

- No listing-page pagination depth was observed in Phase 0 (only two
  specific order pages were fetched directly by URL). **Not measured.**
  SEBI's enforcement-orders section is known (from general use of the site)
  to span many years; a Phase 1 task should fetch
  `sebi.gov.in/enforcement/orders.html`'s listing/pagination the same way
  IBBI's was sampled here, before committing to a backfill timeline.

### CARE / India Ratings / Acuité (AVAILABLE / AVAILABLE_WITH_LIMITS)

- Only one CARE document was fetched in Phase 0. **Not measured.** Each
  agency publishes rationales per rated entity per review cycle (typically
  annual, plus event-driven reviews); a realistic backfill would be scoped
  per company via each agency's company-specific page, not a single global
  archive, and was not sized in Phase 0.

### BSE / NSE (BLOCKED)

- No backfill estimate is meaningful while both are BLOCKED for this tool's
  honestly-identified requests (see `docs/data/source-inventory.md`). This
  is the dominant feasibility risk for the whole project: company
  announcements, shareholding/pledge disclosures, XBRL results, and
  bhavcopy price archives all live primarily on these two exchanges.

## Survivorship (delisted/suspended companies)

- **IBBI: confirmed available.** All four companies in the Phase 0 seed
  under CIRP/insolvency (DHFL, Jet Airways, Reliance Capital, Future
  Retail) have their NCLT order records reachable on `ibbi.gov.in` despite
  being suspended, delisted, or under resolution. This is a genuine
  positive finding, not an assumption.
- **CARE: one positive data point.** The 2019 DHFL rationale (a company
  later delisted) was still reachable in 2026.
- **SEBI: untested.** No delisted company's order was in the Phase 0 seed
  sample.
- **Price data: untested.** No bhavcopy data was downloaded (BSE/NSE
  BLOCKED), so whether rows for delisted/suspended tickers persist in the
  archives could not be checked empirically. This is an open question for
  whatever price-data path Phase 1 ultimately uses.

## Candidate outcome labels

| Label | Supporting source(s) | Coverage observed | Rough count | Status |
|---|---|---|---|---|
| IBBI insolvency admission | IBBI orders/nclt listing | Real (1,685+ pages of orders seen) | ~23,600 order *documents* (not unique admissions) — ESTIMATE | Feasible to extract; needs Phase 1 parsing to deduplicate into unique case admissions |
| Rating downgrade to default | CRISIL/ICRA/CARE/India Ratings rationales | CARE: 1 document fetched; others not fetched | Not counted | CARE available; CRISIL avoided (AI-crawler robots directive); ICRA blocked; India Ratings/Acuité untested |
| SEBI enforcement order | SEBI enforcement/orders section | 2 documents fetched (1 company) | Not counted (no listing pagination observed) | Feasible; volume unmeasured |
| Large price drawdown | BSE/NSE bhavcopy, or an alternative licensed price feed | None — no price data obtained | Not counted | Blocked via exchanges; needs an alternative source, not yet identified |
| Delisting / suspension | BSE/NSE delisted-company lists, or SEBI/exchange delisting notices | None — not tested | Not counted | Blocked via exchanges; alternative not yet identified |

All counts above are **estimates** where given, and explicitly "not
counted" where no real measurement was taken.

## Red-flag category feasibility matrix

See `docs/data/taxonomy-v0.1.md` for category definitions. "Availability"
here is the Phase 0 verdict for the document type each category needs most.

| Category | Needs | Availability | Phase 2+ decision this gap affects |
|---|---|---|---|
| AUD_RESIGN (auditor resignation) | BSE/NSE Reg 30 disclosure, or company IR site | BLOCKED (exchanges); IR sites untested | Whether extraction can rely on exchange filings at all, or must scrape individual company IR sites with per-site rules |
| PLEDGE_UP (promoter pledge increase) | BSE/NSE shareholding/SAST disclosure | BLOCKED | Same as above — pledge data is exchange-only as far as Phase 0 found |
| KMP_EXIT (KMP departure) | BSE/NSE announcement | BLOCKED | Same |
| ID_EXIT (independent director exit) | BSE/NSE announcement | BLOCKED | Same |
| RATING_ACT (rating action) | Rating agency rationale | CARE available; others mixed | Which agencies' sites are worth per-company scraping; whether CRISIL is used at all given the robots.txt judgment call |
| RESULT_DELAY (delayed financial results) | BSE/NSE announcement / XBRL | BLOCKED | Same as AUD_RESIGN |
| AUDIT_QUAL (audit qualification) | Annual report / XBRL | Untested (annual reports mostly linked from exchange filings) | Whether annual reports can be obtained directly from company IR sites, bypassing exchanges |
| FORENSIC (forensic audit ordered/disclosed) | SEBI order, or exchange announcement | SEBI available (confirmed via Gensol) | SEBI alone may not surface every forensic-audit disclosure — most are first announced via exchange filing |
| RPT_GROWTH (related-party transaction growth) | Annual report / XBRL financials | Untested | Same as AUDIT_QUAL |
| GUIDANCE_MISS (guidance vs. actual miss) | Earnings call transcript / investor presentation | Untested — no transcript source verified in Phase 0 | Whether exchange-hosted transcripts (blocked) or company IR sites (untested) will be the path |

The pattern is consistent: **everything that depends on a BSE/NSE
announcement is currently infeasible for this tool**, and company
investor-relations sites are the untested, most promising fallback for
Phase 1 to evaluate first.
