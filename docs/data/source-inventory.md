# Phase 0 Data-Source Inventory

Full machine-readable detail: `data/manifests/sources.yaml`. This document is
the human-readable narrative of the same findings. Every claim below was
checked by an actual HTTP request (robots.txt fetch, reachability probe, or
real document download) on **2026-10-23** (initial Phase 0) or
**2026-10-25** (Correction 1, marked as such below), unless marked
UNVERIFIED/gap. No URL, robots.txt line, or terms-of-use paraphrase here
was assumed — each was opened (the exact URLs are listed under each source
in `sources.yaml`).

**Correction 1 headline finding**: `archives.nseindia.com` — a distinct
NSE subdomain from the blocked `www.nseindia.com` and
`nsearchives.nseindia.com` — serves real NSE equity bhavcopy to our
honestly-identified client. This single discovery is why the Correction-1
seed dataset could include real NSE price data without any BSE/NSE
workaround. See "NSE bhavcopy: a working, unblocked path" below.

## Summary table

| Source | Access method | Terms / redistribution | Verified coverage | Verdict |
|---|---|---|---|---|
| BSE (all subdomains) | HTML + static PDF paths | Not reached (blocked) | Not verified (blocked) | **BLOCKED** |
| NSE (`www.` / `nsearchives.`) | HTML + archives | Not reached (blocked) | Not verified (blocked) | **BLOCKED** |
| **NSE bhavcopy (`archives.nseindia.com`)** | Direct static file paths | Not reached (no page content, only files) | **2016-01 to 2025 (real files downloaded)** | **AVAILABLE_WITH_LIMITS** |
| SEBI | HTML + PDF | Reproduction needs permission; not an open licence | 2025-04 to 2025-07 (seed sample) | **AVAILABLE** |
| IBBI | HTML + PDF | Generic copyright notice; full terms not read (gap) | 2019-07 to 2024-08 (seed sample) | **AVAILABLE** |
| CRISIL Ratings | HTML | Not reviewed — see note below | Not fetched (declined) | **BLOCKED** (judgment call) |
| ICRA | HTML | Not reached (bot-mitigation challenge) | Not verified (blocked) | **BLOCKED** |
| CARE Ratings (CareEdge) | HTML + PDF; real per-company discovery API found in Phase 3 (see addendum) | Copyrighted, all rights reserved | 162 rationale documents across 10 companies, 2003-12-30 to 2026-07-21 (Phase 3 §2.2, up from the single 2019-06-05 seed item) | **AVAILABLE** |
| India Ratings | HTML | Not reviewed (gap) | Not verified | **AVAILABLE_WITH_LIMITS** |
| Acuité | HTML | Not reviewed (gap) | Not verified | **AVAILABLE_WITH_LIMITS** |
| Infomerics | HTML | Not reviewed (gap) | Not verified | **UNCLEAR** |
| Brickwork Ratings | HTML | Not reviewed (gap); regulatory status disrupted 2022-2024 | Not verified | **UNCLEAR** |
| MCA (mca.gov.in) | HTML portal; data.gov.in bulk mirror | Not reached (blocked) | Not verified | **BLOCKED** (mca.gov.in); data.gov.in mirror unverified |
| Alpha Vantage (price API) | REST, API key required | Not reviewed in depth | n/a (no key present) | **AWAITING_KEY** |
| Kaggle NSE/BSE datasets | Web/API, account required | CC0 per publisher tags | n/a (not downloaded) | **REQUIRES_REGISTRATION** |
| Commercial datasets (CMIE, Capitaline, ACE, LSEG, Bloomberg) | Paid subscription | n/a (not attempted) | n/a | **REQUIRES_PAYMENT_OR_LICENCE** |
| Academic datasets | n/a | n/a | n/a | **UNCLEAR** (gap — not identified) |
| Company IR sites (Vakrangee, Jet Airways, Brightcom, + 7 controls) | HTML + PDF, own domains | Not reviewed per-site (gap) | Real documents downloaded from each | **AVAILABLE** |
| DHFL's own site (dhfl.com) | HTML | n/a | n/a | **BLOCKED** (own robots.txt: `Disallow: /`) |

## Headline finding: exchange bot-mitigation, not robots.txt, is the real gate

Both BSE and NSE present permissive-looking or absent robots.txt files, but
their edge infrastructure (Akamai) rejects requests whose User-Agent is not a
recognised browser string:

- **BSE**: our honestly-identified User-Agent got HTTP 403 on *every* path
  tested, including the homepage, `robots.txt` itself, and static PDF asset
  paths (`xml-data/corpfiling/...`, `bseplus/AnnualReport/...`). A plain
  browser User-Agent reached the homepage (HTTP 200).
- **NSE**: the main site (`www.nseindia.com`) returned HTTP 403 for *both*
  our identifying UA and a browser UA (a broader block). Its bulk-archive
  subdomain (`nsearchives.nseindia.com`) served a bhavcopy ZIP to a browser
  UA (HTTP 200) but the identical request with our identifying UA stalled
  mid-TLS-handshake and timed out.

Per the ground rules, we do not send a fake browser identity to get past
this — that is exactly the "stealth / fingerprint-spoofing" technique the
task explicitly rules out, and it also conflicts with our own policy
(§6/ADR-0002) of always sending an honest, identifying User-Agent. **Both
exchanges are therefore marked BLOCKED for this project's acquisition tool**,
even though a human using an ordinary browser can read the same pages. This
is the single biggest constraint on the Phase 0 seed dataset (see
`docs/data/seed-universe.md`) and on the backfill feasibility estimate (see
`docs/data/feasibility-assessment.md`).

## MCA

`mca.gov.in` itself returned an Akamai "Access Denied" page for every
request tried (both UAs), so it is marked BLOCKED. Secondary sources
describe MCA21 company/director master data as free with no login, filed
documents (incorporation papers, annual returns, financials) costing roughly
Rs 25-100 each via a free account, and a free bulk "Company Master Data" ZIP
(28M+ companies) published on `data.gov.in`. **This pricing/bulk-mirror
claim was not independently verified against a live MCA page in Phase 0** —
record it as a promising Phase 1 lead, not a confirmed fact.

## A judgment call: CRISIL Ratings

CRISIL's `robots.txt` is permissive for a generic `*` User-Agent on most
paths, but it explicitly lists `Disallow: /` for a long roster of named
crawlers — including `anthropic-ai`, `claudebot`, `Claude-Web`, `cohere-ai`,
`GPTBot`, `ChatGPT-User`, `PerplexityBot`, `CCBot`, and `bingbot` among
others. This acquisition tool's own User-Agent string is a custom one, not a
literal match for any of those names, so a strict robots.txt parser would
permit the fetch. **We chose not to fetch from CRISIL anyway.** This project
is being built by an AI agent (Claude Code) on the user's behalf, and the
site's robots.txt shows a clear, repeated intent to exclude AI-operated
crawling specifically. Following the letter of the rule while clearly
working against its evident spirit did not seem like the right call. This is
flagged explicitly as a judgment call the user may want to revisit, not a
technical limitation — see "Decisions needing approval" in
`docs/data/acquisition-strategy.md`.

## ICRA

The very first request — fetching `robots.txt` — returned a JavaScript
bot-fingerprinting challenge page (obfuscated script referencing
`cdn.infisecure.com/barracuda.js`, an Imperva-style challenge), not an actual
robots.txt file. This is active anti-automation at the first touchpoint;
marked BLOCKED, no further requests attempted.

## Rating agencies that were reachable but not used

India Ratings, Acuité, Infomerics and Brickwork Ratings all had permissive
or absent `robots.txt` files and reachable homepages, but Phase 0's time
budget did not stretch to locating and verifying a specific company
rationale URL for any of them, nor to reading their terms-of-use pages.
These are credible candidates for Phase 1 and are marked
`AVAILABLE_WITH_LIMITS` / `UNCLEAR` rather than `AVAILABLE`, specifically
because nothing was actually downloaded from them. Brickwork's SEBI
registration was also disrupted 2022-2024 (cancelled, ordered to wind down,
later allowed to resume) — worth knowing before relying on it as a
rating-rationale source; see `sources.yaml` for citations.

## NSE bhavcopy: a working, unblocked path (Correction 1)

Retesting NSE hosts individually (per host, identifying UA only, no
browser-UA comparison this round) turned up `archives.nseindia.com` — a
third NSE subdomain, distinct from both `www.nseindia.com` (BLOCKED,
Akamai 403 for every UA) and `nsearchives.nseindia.com` (now BLOCKED even
harder than in Phase 0's original check — connection refused rather than
a timeout).

Specific static file paths on `archives.nseindia.com` return HTTP 200 to
our honest, identifying User-Agent and real, valid bhavcopy ZIP/CSV
content:

- Legacy format (through 2024-07-05):
  `/content/historical/EQUITIES/<YYYY>/<MON>/cm<DD><MON><YYYY>bhav.csv.zip`
- Current UDiFF format (from 2024-07-08):
  `/content/cm/BhavCopy_NSE_CM_0_0_0_<YYYYMMDD>_F_0000.csv.zip`

Spot-checked dates in 2016, 2019, 2021, and both sides of the 2024-07-08
format change all returned HTTP 200 with valid file content. **One caveat
found by testing, not assumed**: a 1999 date returned the same Akamai
"Access Denied" page seen on the fully-blocked hosts — so this is not a
blanket exemption for the whole host, only for (at least) the 2016-2025
range actually exercised by the Correction-1 seed run. The host's root
page and `/content/` listing are themselves unreachable (connection
failures) — only exact, predictable file paths work. `robots.txt` at this
host returns 404 (no file), so there is nothing to disallow.

This is marked `AVAILABLE_WITH_LIMITS`, not `AVAILABLE`, for two reasons:
only specific file paths (not the whole host) are proven reachable, and
the pre-2016 boundary was not pinpointed.

## Company investor-relations sites (Correction 1, §B2)

SEBI (LODR) Regulation 46(2) requires every listed entity to publish, on
its own website, its annual report, financial results, shareholding
pattern, and credit ratings for outstanding instruments (quoted/paraphrased
from `ca2013.com/lodr-regulation-46/`, cross-checked against SEBI's own
LODR FAQ PDF). It does **not** explicitly require Regulation 30
disclosures (auditor/KMP/director changes) to be mirrored on the website —
that obligation runs primarily through the stock-exchange filing itself —
though many companies publish them voluntarily under their own "News &
Announcements" sections.

Acting on this, each reachable seed/control company's own site was
checked individually (robots.txt + a specific document URL, identifying
UA only):

- **Vakrangee** (`vakrangee.in`): no robots.txt (404, allow by
  convention). Its News & Announcements archive directly links the actual
  2018 Price Waterhouse & Co auditor-resignation letter, the company's own
  "update" on the resignation, and its Reg 30 intimation to the exchange —
  all three downloaded and hash-verified.
- **Jet Airways** (`jetairways.com`): no robots.txt (404). A March-2022
  shareholding-pattern PDF was found and downloaded directly from the
  company's own domain.
- **Brightcom Group** (`brightcomgroup.com`): robots.txt disallows only
  `/wp-admin/`. The FY2018-19 annual report PDF was downloaded directly.
- **DHFL** (`dhfl.com`) is the one exception: although the site is
  reachable, its **own robots.txt explicitly disallows every generic
  crawler** (`User-agent: *` / `Disallow: /`). Per ADR 0002 we always
  honour a disallow, so nothing is fetched from dhfl.com, full stop — DHFL
  documents in this project come from IBBI and CARE instead.
- **Reliance Capital** (`reliancecapital.co.in`) and **Gensol Engineering**
  (`gel.gensol.in`) were both unreachable (connection failures) when
  retested — no alternative primary IR-site source was found for either
  within budget; see `docs/data/manual-download-checklist.md` for the
  resulting gaps.

Seven control companies (one or two per sector named in the brief) all had
open or non-blanket robots.txt files and a real document (shareholding
pattern, annual report, or investor presentation) downloaded from each:
LIC Housing Finance and PNB Housing Finance (housing finance, vs. DHFL),
SpiceJet (aviation, vs. Jet Airways — IndiGo's `goindigo.in` was
unreachable and was dropped in favour of SpiceJet), Avenue Supermarts/DMart
(retail, vs. Future Retail), Thermax (power equipment, vs. CG Power),
Suzlon Energy (renewables, vs. Gensol), and Mastek (IT services, vs.
Vakrangee). Selection rule and per-company reasoning:
`docs/data/seed-universe.md`.

## Price-data alternatives (Correction 1, §B7)

- **Alpha Vantage**: free tier is 25 requests/day with NSE data reportedly
  discontinued (BSE-only remains), per public documentation not
  independently re-verified. Requires a free API key. `.env`/`.env.example`
  were checked for a pre-existing key (`grep -i PRICE_API_KEY`) — none
  found — so per instructions this is recorded as **AWAITING_KEY** and no
  request was made. Moot in practice: `archives.nseindia.com` (above)
  already provides real NSE price data with no account.
- **Kaggle NSE/BSE datasets**: several (e.g. "NSE India Stock Data
  1990-2021", "NSE Stock Market Daily Update Bhavcopy") are tagged CC0
  (public domain) by their publishers per Kaggle's own listing — found via
  search, not opened, since downloading requires a Kaggle account and
  ground rules forbid creating one. **REQUIRES_REGISTRATION**.
- **Manual bhavcopy import** (the brief's option (c)): turned out
  unnecessary — the automated `archives.nseindia.com` path above covers
  the seed windows directly.

## Addendum (2026-10-28, Phase 3 §2.2): CARE rationale coverage broadened

Phase 0/1 had exactly one CARE document (the DHFL rationale above),
hand-found. Phase 3 §2.2 looked for a real, crawlable, compliant discovery
mechanism and found one -- and also found a real limit it does not clear.

**What does NOT exist**: a sitewide, crawlable, date-range listing of
rating rationales. `/industry/press-release/24` (reachable from the
site's own nav and sitemap) only filters *industry research* reports by
month/year and is itself client-rendered with no discoverable date-range
API for rationale documents specifically. This was checked directly
(fetched the raw HTML, grepped for inline `<script>`/AJAX hooks) before
concluding it does not exist, not assumed.

**What DOES exist**, same-origin, read directly out of the site's own
inline `<script>` for its header search widget (not guessed): `GET
/header/searchlist?cinput=<name>` (name resolution) -> `GET
/pryear?companyName=<id>` (years on file) -> `GET
/getSearchprdocument?companyName=<id>&YearID=<year>` (the documents
themselves, with real filenames under `/upload/CompanyFiles/PR/`).
robots.txt is fully permissive (quoted above) and this is the exact path
a real browser's search box takes.

**Real result, driving this lookup from the 15-company SEED-track universe
(`docs/data/seed-universe.md`)**, `ledgerlight/ingestion/care.py`,
2026-10-28 run (`docs/phase-3/evidence/care-discovery-run1.log`):
- 15 companies queried, 11 matched a CARE company record by name
  (`rapidfuzz.token_sort_ratio` on corporate-suffix-stripped names, floor
  75), 161 new rationale/press-release PDFs fetched (0 unchanged, 0
  blocked, 0 errors) across 10 of those 11 (CG Power matched but has zero
  PR documents on CARE's file). Real per-company counts, from the
  `documents` table: PNB Housing 47, LIC Housing 44, Future Retail 28,
  Suzlon 15, DMart 12, Vakrangee 4, SpiceJet 4, Gensol 4, Jet Airways 2,
  Thermax 1.
- **4 of 15 did not match, confirmed as a real source limitation, not a
  matcher bug** (each re-checked by hand with a direct `curl` against the
  live API after the run):
  - **Dewan Housing Finance**: zero search results under that name or
    "DHFL". CARE's live index reflects *current* entity names only; DHFL's
    post-CIRP successor (`Piramal Capital & Housing Finance Limited`,
    confirmed present in CARE's search) does not itself reference DHFL in
    its own "erstwhile" name, so there is no live name path back to the
    original entity. The one DHFL rationale already in the seed (fetched
    in Phase 0 by a hand-found direct URL) remains reachable; it just is
    not *discoverable* via this mechanism any more.
  - **Reliance Capital**: zero search results under that exact name;
    querying the shorter prefix "Reliance" returns real candidates but
    none named "Reliance Capital" (alphabetically, the result set jumps
    straight from "Business Broadcast..." to "Chemicals..."). Same
    pattern as DHFL: a large NBFC that went through CIRP resolution
    (2024-2025) and appears to no longer carry its pre-resolution name in
    CARE's live index.
  - **Mastek**: one real candidate found, "Mastek Engineering Private
    Limited" -- a *different* legal entity from the listed parent (NSE:
    MASTEK) this project tracks, correctly scored 50/100 (well below the
    75 floor) and excluded. CARE's index has no record under "Mastek"
    for the listed parent itself at all.
  - **Brightcom Group**: zero search results under that name or the
    shorter "Brightcom" alone. No evidence CARE has ever rated this
    company (plausible: Brightcom's governance issue was a SEBI
    accounting/disclosure matter, not a rated-debt event) -- recorded as
    a gap, not asserted as a confirmed absence.
- **sources.yaml's `care.verified_coverage`** is updated to this real
  162-document, 2003-12-30 to 2026-07-21, 10-company result (see that file).

## Commercial and academic datasets

Per instructions, commercial datasets (CMIE Prowess, Capitaline, ACE Equity,
LSEG, Bloomberg) are recorded as licensing alternatives only — no access was
attempted. No open academic dataset on Indian corporate governance,
fraud, or default with an **explicit** licence was identified within the
Phase 0 research budget; this is a gap (nothing was found to include), not a
confirmed absence.
