# Data Quality (Phase 3)

Real coverage and known limitations of this project's data, as of 2026-10-31. Every
figure below is a direct query result, not an estimate -- see each section's own evidence
pointer.

## price_bars (bhavcopy)

EQ series: **2016-01-01 to 2026-10-30**, 2,370,656 real rows (`docs/phase-3/phase-3-report.md`
§2.1). 2016-01-01 is the exhaustively-confirmed earliest real NSE bhavcopy coverage
boundary -- not a project limitation, NSE itself has nothing earlier in a compliant
archive form. A real parsing-pipeline gap for 2016-01-01 to 2017-01-04 was found and
backfilled during §2.1.

## Companies and identifiers

6,278 real `Company` rows, 14,636 `company_identifiers` rows. Two real, previously-
undetected bugs were found and fixed while building §4's feature engine (full writeup:
`docs/phase-3/progress.md`'s §4.0 entry):

1. **Stale `valid_from` windows**: bootstrap's idempotency meant 2,936 identifiers never
   got their window widened after later backfills added earlier real history. Fixed:
   2,849 corrections applied (87 correctly left stale by a symbol-reuse guard -- genuine
   ambiguous cases, not errors).
2. **Duplicate companies**: the fix above's own bootstrap re-run recreated the Sec2.4
   fragmentation bug at small scale (94 ISIN-groups). Fixed with a self-healing merge pass
   now run on every bootstrap.

Both fixes are permanent (self-healing on every future `bootstrap_companies.py` run), not
one-time patches.

## Document corpus, by source

| source_id | real documents | known_at range |
|---|---|---|
| `nse_archives` | 2,195 | 2015-12-31 to 2026-10-29 |
| `care` | 162 | 2003-12-30 to 2026-07-21 |
| `ibbi` | 145 (growing -- crawl in progress, see below) | 2017-08-17 to 2026-10-25 |
| `sebi` | 84 | 2009-06-02 to 2026-05-28 |
| `*_ir` (company investor-relations sites, 9 sources) | 1 each except pnbhousing_ir (4), suzlon_ir (4), vakrangee_ir (3) | all `known_at` clustered at 2026-10-25 -- see the known_at-basis caveat below |

## Known, disclosed caveats

- **`known_at_basis` for non-reliable sources**: a document from a source NOT in
  `RELIABLE_PUBLISHED_AT_SOURCES` (`sebi`, `ibbi`, `care`, `nse_archives`) gets
  `known_at = retrieved_at`, not its own real publish date -- a deliberate, conservative
  Phase 1 design choice (see `ledgerlight.db.temporal`). Real consequence found while
  building §4.3: every `*_ir` (investor-relations) document in this corpus was fetched in
  one narrow window (2026-10-25), so any trailing-window feature built from them is a
  one-time step function pinned to that fetch date, not a real temporal signal. Disclosed
  in `ledgerlight/modelling/seed_governance_features.py` and confirmed in the real built
  snapshots (Vakrangee's trailing-12m AUD_RESIGN count is 0 every month except 2026-10-31).
- **CARE/rating coverage is SEED-track-only**: CARE discovery (§2.2) was driven by the
  15-company SEED-track universe, never broadened to the full currently-listed universe.
  `RATING_DOWNGRADE_D` (outcomes) and the rating RULE-VERIFIED features (§4.2) are
  therefore only meaningful for those 15 companies.
- **No structured pledge-level source**: confirmed absent from this project's real corpus
  (checked, not assumed) -- §4.3's SEED-track features do not approximate it from
  text-derived `PLEDGE_UP` candidates.
- **No real forward-guidance statements anywhere in the corpus**: confirmed by an
  exhaustive keyword search of all 4,759 real pages (§5, `docs/modelling/guidance.md`).
  `GUIDANCE_MISS` has no extraction machinery as a result.
- **Financial-statement extraction excluded**: only 2 real annual-report documents exist
  in the corpus; a real accuracy check (manual, 7 samples) found ~40-50% correctness,
  well short of the brief's 90% bar (§4.3).
- **Governance events are 100% CANDIDATE tier, 0% VERIFIED**: confirmed by direct query,
  project-wide, matching Phase 1 §1.5's finding that no event type clears the
  gold-reliability bar.

## IBBI full-universe discovery coverage

**Pending.** The full-universe IBBI discovery crawl (`scripts/ibbi_universe_discovery.py`)
was still running as of this document's last update (145 real IBBI documents, growing).
Per the user's explicit condition: this section must be filled with the crawl's real,
final date/company coverage once it finishes or is honestly stopped, BEFORE any §6/§7
training or backtest work proceeds. Do not fill this section with an estimate.
