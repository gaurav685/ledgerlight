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

### NSE bhavcopy via `archives.nseindia.com` (AVAILABLE_WITH_LIMITS — Correction 1)

- **Observed directly, not estimated**: Correction 1 downloaded 200 real
  bhavcopy files (a twice-monthly sample, Jan 2017 - Sep 2025) in a single
  run. Elapsed time was consistent with the 2-second default per-host rate
  limit (~230 requests × 2s ≈ 7-8 minutes, matching what was observed).
- **Full daily backfill estimate**: roughly 252 trading days/year ×
  ~8.75 years (2017-2025) ≈ **~2,200 daily files** for this single window;
  for a full 2010-present backfill (~16 years) ≈ **~4,000 files**.
  4,000 × 2s ÷ 3600 ≈ **~2.2 hours** of pure rate-limited sequential
  fetching — trivially feasible.
- Pre-~2016 coverage via this exact path is **not confirmed** (a 1999
  spot-check was blocked); an older per-date naming convention or a
  different host may be needed for 2010-2015, which was not investigated.

### BSE / NSE announcements, shareholding, XBRL (still BLOCKED)

- No backfill estimate is meaningful while both exchanges' announcement/
  filing sections are BLOCKED for this tool's honestly-identified requests
  (see `docs/data/source-inventory.md`). **Price data is no longer part of
  this risk** (resolved above); governance-event announcements,
  shareholding/pledge disclosures, and XBRL results remain exchange-only
  as far as Phase 0 + Correction 1 found.

### Company IR sites (AVAILABLE for some companies — Correction 1)

- Directly observed, not estimated: 3 of 5 event companies retried
  (Vakrangee, Jet Airways, Brightcom) had a reachable IR site yielding a
  real document; 2 (Reliance Capital, Gensol) were unreachable; 1 (DHFL)
  is reachable but its own robots.txt disallows all crawling. All 7
  control companies tried had a reachable, usable IR site.
- **This is not a general solution**: it required a human (well, an AI
  research pass) to individually locate each company's specific document
  URL via web search — there is no single listing/index page analogous to
  IBBI's `orders/nclt`. A per-company backfill at scale would need either
  a directory of IR-site URLs maintained manually, or a web-search-based
  discovery step, neither of which was built in Phase 0.

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
- **Price data (file-level): confirmed available (Correction 1).**
  Bhavcopy files dated after DHFL's, Jet Airways', Reliance Capital's, and
  Future Retail's respective CIRP-admission dates were all downloaded
  successfully from `archives.nseindia.com` — the files themselves exist
  and are reachable post-event. **Row-level** survivorship (does that
  specific ticker's row still appear inside each file, as opposed to being
  dropped from the listing) was not parsed/checked in Phase 0 — the CSV
  content was not opened and searched. This is a precise, bounded Phase 1
  task (parse ~200 already-downloaded CSVs for 4 known symbols), not a new
  access problem.

## Candidate outcome labels

| Label | Supporting source(s) | Coverage observed | Rough count | Status |
|---|---|---|---|---|
| IBBI insolvency admission | IBBI orders/nclt listing | Real (1,685+ pages of orders seen) | ~23,600 order *documents* (not unique admissions) — ESTIMATE | Feasible to extract; needs Phase 1 parsing to deduplicate into unique case admissions |
| Rating downgrade to default | CRISIL/ICRA/CARE/India Ratings rationales | CARE: 1 document fetched; others not fetched | Not counted | CARE available; CRISIL avoided (AI-crawler robots directive); ICRA blocked; India Ratings/Acuité untested |
| SEBI enforcement order | SEBI enforcement/orders section | 2 documents fetched (1 company) | Not counted (no listing pagination observed) | Feasible; volume unmeasured |
| Large price drawdown | NSE bhavcopy (`archives.nseindia.com`) | **Real: 200 files downloaded, Correction 1** | Not yet counted (row-level parsing not done) | Source resolved; drawdown computation is a Phase 1 parsing task, not an access problem |
| Delisting / suspension | BSE/NSE delisted-company lists, or SEBI/exchange delisting notices | None — not tested | Not counted | Still blocked via exchange listing pages; alternative not yet identified (bhavcopy row *absence* over time could proxy this once parsed) |

All counts above are **estimates** where given, and explicitly "not
counted" where no real measurement was taken.

## Red-flag category feasibility matrix

See `docs/data/taxonomy-v0.1.md` for category definitions. "Availability"
here is the Phase 0 verdict for the document type each category needs most.

| Category | Needs | Availability | Phase 2+ decision this gap affects |
|---|---|---|---|
| AUD_RESIGN (auditor resignation) | BSE/NSE Reg 30 disclosure, or company IR site | BLOCKED (exchanges); IR site worked for Vakrangee (verified reachable; download itself blocked by a TLS chain issue, now fixed — see ADR 0002 addendum) | Per-company IR scraping is viable but needs per-site discovery; no single index exists |
| PLEDGE_UP (promoter pledge increase) | BSE/NSE shareholding/SAST disclosure, or company IR site | BLOCKED (exchanges); partially available via IR sites (Jet Airways, SpiceJet, LIC Housing, PNB Housing, Mastek shareholding patterns all downloaded) but only for companies whose IR site happens to publish it; pre-event-date patterns specifically were often not found (see manual-download-checklist.md) | Same as AUD_RESIGN — plus: current IR-site patterns are usually the *latest* quarter, not the historical quarter needed around a past event |
| KMP_EXIT (KMP departure) | BSE/NSE announcement | BLOCKED; not tested via IR sites in Correction 1 | Same as AUD_RESIGN |
| ID_EXIT (independent director exit) | BSE/NSE announcement | BLOCKED; not tested via IR sites in Correction 1 | Same as AUD_RESIGN |
| RATING_ACT (rating action) | Rating agency rationale | CARE available; others mixed (unchanged from Phase 0) | Which agencies' sites are worth per-company scraping; whether CRISIL is used at all given the robots.txt judgment call |
| RESULT_DELAY (delayed financial results) | BSE/NSE announcement / XBRL | BLOCKED; not tested via IR sites | Same as AUD_RESIGN |
| AUDIT_QUAL (audit qualification) | Annual report / XBRL | **Available via IR site for at least 2 companies** (Brightcom FY2018-19, Thermax 44th annual report, both downloaded directly) | Annual reports are one of the more reliably IR-site-published document types per Reg 46 — a promising category for Phase 1 |
| FORENSIC (forensic audit ordered/disclosed) | SEBI order, or exchange announcement | SEBI available (Gensol, confirmed; a CG Power-related SEBI document also found, exact type unreviewed) | SEBI alone may not surface every forensic-audit disclosure — most are first announced via exchange filing |
| RPT_GROWTH (related-party transaction growth) | Annual report / XBRL financials | Same annual reports as AUDIT_QUAL could supply this; not specifically extracted in Correction 1 | Same as AUDIT_QUAL |
| GUIDANCE_MISS (guidance vs. actual miss) | Earnings call transcript / investor presentation | One investor presentation downloaded (DMart, control company) — not an earnings-call transcript specifically; still untested for any event company | Whether exchange-hosted transcripts (blocked) or company IR sites (partially promising per DMart) will be the path |

The pattern has shifted since Phase 0: **price data and annual reports
are now demonstrated feasible** via `archives.nseindia.com` and company
IR sites respectively. KMP_EXIT, ID_EXIT, RESULT_DELAY and most PLEDGE_UP
history (specifically the pre-event quarter, not just the latest one)
remain dependent on BSE/NSE announcements with no confirmed alternative.
