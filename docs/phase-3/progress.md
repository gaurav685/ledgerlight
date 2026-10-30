# Phase 3 Progress

Read this and `docs/phase-3/brief.md` first, at the start of any session continuing this
phase. This file is updated at every checkpoint and before stopping -- if it says
something is done, it is done and committed; if it says something is in progress, the
exact next step is below, not left to be re-derived.

## Sections done

- **§0 ground rules**: understood, applied throughout (see each commit's reasoning).
- **§1 preflight, selection fix, detector hardening**: COMPLETE.
  - 1.1 baseline, 1.2 frozen eval data + guard, 1.3 gold-only per-class selection,
    1.4 detector hardening (+ a real extraction-pipeline false-positive fix), 1.5 event
    reliability tiers (no event type meets the bar), 1.6 knowledge stats -- all in
    `docs/phase-3/phase-3-report.md` §1, with raw evidence under `docs/phase-3/evidence/`.
  - §1 close-out (this continuation's part A): frozen-TEST-split consultation disclosed
    (see `docs/modelling/event-reliability.md`'s dedicated section) -- `AUD_RESIGN`'s test
    metrics are marked "test split consulted during development, not held-out"; real
    before/after gold-validation and final test tables printed and committed.
  - Commits: `1d2b30c`, `816407a`, `6dfd6de`, `5518d16`, `367cb97` (all `phase-2:` prefix
    per this phase's own instruction for §1 work).
- **Part B (this continuation)**: `docs/phase-3/brief.md` (the full original brief +
  this continuation's addendum, saved verbatim) and this progress file -- both written and
  committed (`39e5e76`).
- **§2.2 CARE rationale broadening**: COMPLETE. `ledgerlight/ingestion/care.py` (new
  module) found and uses CARE's real per-company discovery API (not guessed -- read out of
  the site's own header-search widget script); driven by the 15-company SEED-track
  universe. Real run: 11/15 companies matched, 161 new documents fetched (162 total with
  the pre-existing DHFL seed item), 0 errors. 4/15 unmatched, each confirmed by hand as a
  real CARE-side limitation (not a matcher bug) -- see `docs/phase-3/phase-3-report.md` §2.2
  and `docs/data/source-inventory.md`'s 2026-10-28 addendum for the full detail on each.
  `tests/test_care_ingestion.py` (6 tests, all passing). `data/manifests/sources.yaml`'s
  `care` entry updated to the real coverage. New Dagster op/job `care_discovery`
  (`python scripts/ingest.py care_discovery`). Name-matching logic and the SEED-track
  company list were factored out to `ledgerlight/ingestion/name_matching.py` and
  `.seed_track.py` once §2.3 needed the same logic (see below) -- `tests/test_name_matching.py`.
- **§2.3 IBBI NCLT order broadening**: COMPLETE. `ledgerlight/ingestion/ibbi.py` (new
  module) uses IBBI's own real Drupal-Views order listing (`/orders/nclt?title=<name>&page=<n>`),
  driven by the same 15-company SEED-track universe. First live run hit a real bug
  (IBBI returns a hard 404 for an out-of-range page, not an empty table; the first
  pagination implementation treated that as fatal and discarded already-collected rows
  -- see `docs/phase-3/phase-3-report.md` §2.3 for the full writeup) -- fixed, with a
  regression test, before trusting any output. Real second run: 6/15 companies matched,
  51 new documents fetched (55 total with the 4 pre-existing seed items), 0 errors.
  **Real, surprising finding**: SpiceJet (Phase 0's "no known event" aviation control vs.
  Jet Airways) actually has 8 distinct NCLT insolvency petitions filed against it
  (2021-2026) -- reported plainly as a reason to revisit that control-group selection, not
  resolved unilaterally (see "Open defects" below). `tests/test_ibbi_ingestion.py` (7
  tests, all passing). `data/manifests/sources.yaml`'s `ibbi` entry updated. New Dagster
  op/job `ibbi_discovery` (`python scripts/ingest.py ibbi_discovery`).
- **§2.3 SEBI enforcement-order broadening**: COMPLETE. `ledgerlight/ingestion/sebi.py`
  (new module) uses SEBI's own real "Search by Title, Keywords, Entity Name" AJAX
  endpoint (`smid=0`, all-categories scope), driven by the same 15-company SEED-track
  universe. A WAF block on the first raw attempt was resolved with ordinary session
  continuity (cookie + Referer + X-Requested-With), not defeated -- see
  `docs/phase-3/phase-3-report.md` §2.3 for why this is not the kind of fingerprinting
  evasion the ground rules forbid. First live run hit a real bug (some SEBI hrefs are
  relative paths, not absolute URLs -- `httpx.UnsupportedProtocol` on 42/84 attempts);
  fixed with `urljoin`, regression test added, before trusting any output. Real second
  run: 13/15 companies matched, 45 new documents fetched (84 total), 0 errors.
  `tests/test_sebi_ingestion.py` (7 tests, all passing). `data/manifests/sources.yaml`'s
  `sebi` entry updated. New Dagster op/job `sebi_discovery`
  (`python scripts/ingest.py sebi_discovery`).
- **§2.1 bhavcopy backfill**: COMPLETE, verified. The original `2012-01-01 2026-10-28`
  run was killed by a machine restart (which also took the local Docker stack down)
  before reaching its forward end, stuck at 2023-07-20 in
  `$TEMP/backfill_2012_present.log`. On resuming this session (2026-10-30): Docker
  Desktop and the Postgres/Garage containers were restarted
  (`docker compose --env-file .env -f infra/docker-compose.yml up -d`; both came back
  healthy with their existing volumes intact). Real findings:
  - **Earliest-date boundary exhaustively confirmed, not just spot-checked**: zero
    successful fetches exist in the `documents` table for 2012-2015; direct `curl`
    spot-checks return 403 for 2012-06-15/2014-01-10 and 200 for 2016-06-01/2016-12-30.
    Real earliest date: **2016-01-01**. The brief's 2012 target is not reachable on this
    path -- a real source limit, not a gap to keep chasing.
  - **A real parsing-pipeline gap was found and fixed**: 2016-01-01 to 2017-01-04
    bhavcopy files were fetched into the document store but never parsed into
    `price_bars` (a separate step, `ledgerlight.processing.price_loader`, not part of the
    fetch job). `scripts/process.py` (the full, idempotent reprocess over every
    `DocumentVersion`, including the ~350 new CARE/IBBI/SEBI PDFs from §2.2/§2.3 that had
    never been through page extraction) closed the 2016 part of this gap (confirmed
    directly: `price_bars`' minimum moved from 2017-01-05 to 2016-01-01) but never reached
    the newest (forward-extension) bhavcopy files. Its own completion evidence was lost
    separately by an operator mistake (its placeholder log file was deleted while still an
    open redirect target); the more likely real cause of it stopping was a low-memory
    condition in this environment -- directly confirmed later, when a much smaller scoped
    job was explicitly killed with "system is running low on memory" (no evidence that
    job itself leaked memory; general desktop load from other running applications was
    the likely trigger). Rather than re-run the full heavy reprocess, a small scoped
    script (parsing only the `DocumentVersion`s still missing a `price_bars` row,
    committing after every file) closed the remaining gap in two passes, the second
    narrower after the same low-memory kill interrupted the first.
  - **Forward extension completed cleanly**: `python scripts/backfill.py 2025-09-23
    2026-10-30` (run after the Docker stack was back up): 289 business days attempted,
    272 new files, 17 correctly-identified non-trading days, 0 errors, 0.501 req/s
    (`$TEMP/backfill_forward_ext.log`).
  - **Real, final, directly-verified coverage**: `price_bars` now spans **2016-01-01 to
    2026-10-30, 3,020,745 rows** -- re-queried after the scoped parse's clean completion
    (`processed: 34, rows_upserted: 125186, rows_quarantined: 0, errors: 0` for its final
    pass).

- **§2.4 entity-link reporting**: COMPLETE, including a real, deeper fix the user
  explicitly asked for after two check-in questions. Initial result
  (`docs/phase-3/evidence/entity-link-report-run1.log`): care 133/162, ibbi 25/55,
  sebi 67/84 -- every unmatched document traced to one of three BSE codes (DHFL,
  Future Retail, Reliance Capital), because `company_identifiers` had only 6 `BSE_CODE`
  values (bootstrap is NSE-bhavcopy-only). Checking whether these three already had a
  usable NSE_SYMBOL/ISIN surfaced a second, much bigger, unrelated bug: `Company` rows
  were created **per ISIN, not per real company** -- DHFL alone was fragmented into 29
  rows; a full scan found **422** real companies fragmented this way (1,122 duplicate
  rows), overwhelmingly NBFCs/bond issuers. Fixed, with the user's explicit sign-off:
  - `ledgerlight/ingestion/company_grouping.py` (new): union-find over ISIN/symbol
    co-occurrence. `tests/test_company_grouping.py` (6 tests).
  - `scripts/bootstrap_companies.py` rewritten to use the corrected grouping.
  - `scripts/migrate_company_dedup.py` (new): one-time migration, `--dry-run` first
    (422 groups found, plan written to `docs/phase-3/evidence/company-dedup-dry-run.json`,
    spot-checked by hand -- every multi-symbol group traced to one real company, e.g.
    REC Limited's ~13 bond series, Indiabulls Housing Finance's 2023 rename to Sammaan
    Capital). Tables backed up (`../ledgerlight-backups/pre-company-dedup-backup.sql`)
    before `--apply`. Real result
    (`docs/phase-3/evidence/company-dedup-apply-run1.log`): 422 groups fixed, 1,122
    duplicate rows deleted, 2,555 identifiers regenerated, 0 existing
    filings/events/label_items/entities needed re-pointing. `companies` row count now
    exactly equals distinct `display_name` count -- zero duplicates remain.
  - `ledgerlight/ingestion/seed_track.py` updated (DHFL/Reliance Capital/Future Retail
    now carry `nse_symbol`); the 76 already-fetched Document rows (19+14+43) had
    `nse_symbol` added directly, dry-run first.
  - **Final result** (`docs/phase-3/evidence/entity-link-report-run2-post-fix.log`): all
    301 CARE/IBBI/SEBI documents now auto-link -- care 162/162, ibbi 55/55, sebi 84/84.

## Not yet started

§3 (outcome definitions, frozen before any training), §4 (point-in-time features +
migrations), §5 (guidance extraction), §6 (LightGBM models), §7 (walk-forward eval +
leakage controls), §8 (scoring + storage), §9 (rest of the Dagster pipeline + commands),
§10 (tests), §11 (documentation set), §12 (run and verify), §13 (final commit/backup for
§2-15, `phase-3:` prefix), §14 (exit gates), §15 (final report).

## Exact next step

1. Begin §3: freeze the outcome definitions (hashed, stored in `model_registry`) *before*
   any training code runs, per the brief's own ordering. Primary outcome: IBBI CIRP
   admission OR rating downgrade to D, within 12 months. Secondary outcomes: severe
   drawdown, SEBI order, bhavcopy disappearance. Handle censoring explicitly.
   `docs/modelling/outcomes.md` + a spec file; `docs/modelling/outcome-evidence-review.csv`;
   a release-gate addition. DHFL/Future Retail/Reliance Capital now auto-link cleanly
   (§2.4's fix), so their IBBI-based primary-outcome positives can be populated via the
   normal auto-link path -- no special-casing needed.
   ICRA and CRISIL stay excluded (CRISIL by its own exclusion terms, per `docs/data/
   source-inventory.md`).
2. If a future session hits an apparent background-job hang with near-zero CPU growth on
   a heavy document/OCR batch: check this environment's free memory
   (`Get-CimInstance Win32_OperatingSystem`) and the Docker/Garage container logs for
   fresh timestamps before assuming a real code bug -- this session's `scripts/process.py`
   stall and a follow-up scoped job's explicit low-memory kill both turned out to be a
   genuine environment resource constraint, not application-level hangs. Prefer smaller,
   explicitly-committed, narrowly-scoped batch jobs over one large reprocess when memory
   is tight.

## Open defects / known limitations (not yet resolved)

- `uv.lock` was never regenerated in this environment (`uv` not on `PATH`) -- same gap
  disclosed in every phase report since Phase 1. ML dependencies were pip-installed
  directly into `.venv`.
- `AUD_RESIGN`'s frozen-test metrics are not a clean held-out result (test-split
  consultation during §1.4 hardening, disclosed in full in
  `docs/modelling/event-reliability.md`). A genuinely fresh, never-viewed replacement
  test set for `AUD_RESIGN` is a decision for a human, not made unilaterally.
- No event type currently meets the §1.5 reliability bar -- every EVENT-CANDIDATE
  feature in §4 must stay in the ablation arm, unverified, per the feature policy. This
  is expected to remain true through most of Phase 3 given this corpus's size; it is not
  a bug, just the honest state of evidence.
- **SpiceJet's Phase 0 control-group selection should be revisited** (found in §2.3's
  IBBI discovery, 2026-10-28): SpiceJet was picked as the "no known distress event"
  aviation control vs. Jet Airways, but a real search now finds 8 distinct NCLT
  insolvency petitions filed against it (2021-2026). Whether any was actually admitted
  into CIRP (vs. filed then settled/withdrawn) has not been reviewed. Not resolved
  unilaterally -- flagged for a human decision on whether SpiceJet should be dropped,
  reclassified, or kept with this caveat noted in any later modelling that uses it.
- SEBI's (§2.3) `pdf_unresolved=3`: three real search results whose landing-page HTML
  did not contain the expected `<iframe src="...?file=...">` PDF-embed pattern. Skipped
  and counted, not guessed at -- a real, small, disclosed gap in that source's coverage,
  not yet individually investigated.
- ~~BSE_CODE bootstrap gap (§2.4)~~ -- **RESOLVED** 2026-10-30: DHFL/Future
  Retail/Reliance Capital now carry `nse_symbol` and auto-link cleanly; see "§2.4" above
  for the fix (which also resolved the much larger 422-company fragmentation bug). The
  underlying `BSE_CODE` scarcity in `company_identifiers` (still only 6 values) remains a
  real, disclosed gap for any FUTURE delisted company not already covered by an
  NSE_SYMBOL/ISIN fallback -- not urgent now that the three companies this project
  actually needs are fixed, but worth remembering if a new delisted company enters the
  SEED-track universe later.
