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

- **§3 outcome definitions**: COMPLETE as a spec, PARTIAL as populated data (disclosed,
  not hidden). `data/taxonomy/outcomes-v1.0.yaml` (new taxonomy, loaded via
  `make outcomes-taxonomy-load`, deliberately separate from the red-flag taxonomy) defines
  5 event types: `IBBI_CIRP_ADMISSION`, `RATING_DOWNGRADE_D` (the primary outcome's two
  OR'd triggers), `SEBI_ORDER_AGAINST_COMPANY`, `SEVERE_DRAWDOWN`, `BHAVCOPY_DISAPPEARANCE`
  (secondary). `scripts/compute_drawdown_threshold.py` computed the real severe-drawdown
  threshold from `price_bars` (p5 of the pooled, ETF-filtered, winsorized 12-month
  cross-sectional excess-return distribution, 2016-2026: **-48.69pp** filtered vs -55.73pp
  raw, both disclosed). `scripts/populate_outcomes.py` populated real `Outcome` rows with
  `EventField` evidence citations for the three document-evidenced types; a real
  duplicate-grouping bug (DHFL's one real case split into 4 by exact-string case-number
  matching across differently-formatted real documents) was found by spot-checking DHFL
  directly and fixed via `_normalize_case_number()` -- `IBBI_CIRP_ADMISSION` dropped from
  33 to 20 project-wide (DHFL 4 to 3). Real current counts:
  `SEVERE_DRAWDOWN` 7,462, `BHAVCOPY_DISAPPEARANCE` 801, `SEBI_ORDER_AGAINST_COMPANY` 69,
  `IBBI_CIRP_ADMISSION` 20, `RATING_DOWNGRADE_D` 14. The full narrative spec is
  `docs/modelling/outcomes.md`; the machine-readable spec is
  `data/modelling/outcomes-v1.0.json` (sha256
  `d879a2874d063b0025820ce52223e443b5b14d7c8746aa8d9e3117e4f3503e1b`, to be stored in
  `model_registry` for every experiment); every positive primary-outcome row is listed
  with its evidence citation in `docs/modelling/outcome-evidence-review.csv`, pending the
  human spot-check now tracked as its own `docs/release/release-gates.md` entry. Censoring
  (unknown trading stop, end-of-window observation) is handled explicitly in both the
  narrative doc and the machine-readable spec's `censoring_policy` block -- never silently
  imputed as a negative. **Two coverage gaps are disclosed, not hidden**: the full-universe
  IBBI discovery crawl (`scripts/ibbi_universe_discovery.py`) was still running as of this
  commit (2,617 currently-listed companies at IBBI's own rate limit) -- counts above will
  change on re-run; and CARE rating discovery was NOT broadened beyond the 15-company
  SEED-track universe in this pass (only IBBI discovery was, per the user's explicit
  decision), so `RATING_DOWNGRADE_D` coverage stays SEED-track-only for now. Commit:
  `ff55920` (outcomes rows) plus this `phase-3:` doc commit.

- **§4.0 real data-integrity bug found and fixed (stale `company_identifiers.valid_from`)**:
  COMPLETE. While building §4's price-feature engine (joining `price_bars` to `company_id`),
  found that 1,484 of 3,764 real EQ symbols (39%) and 1,452 ISINs had a `valid_from` LATER
  than their own real earliest EQ trade_date, by up to 613 days -- a naive join silently
  dropped 393,553 real EQ rows (16.6% of the total) from company-keyed analysis. Root cause:
  `scripts/bootstrap_companies.py` is idempotent (skips already-bootstrapped identifiers), so
  identifiers bootstrapped before the §2.1 bhavcopy backfill (which filled the real
  2016-01-01..2017-01-04 parsing-gap and other earlier history) never got their `valid_from`
  refreshed. Confirmed by root cause, not just pattern: most stale windows were stale by
  exactly 370 days, matching that known gap precisely.
  - User-approved fix, with four mandatory conditions: (1) a SYMBOL-REUSE GUARD -- a window
    widens only if every real price_bars row in the newly-covered period shares the same
    paired (symbol, isin) with the already-trusted period just after it
    (`ledgerlight/ingestion/identifier_window_repair.py`'s `check_widen_guard`); (2) a real
    audit trail (`identifier_window_corrections` table, migration `40592218ac8b`) recording
    every correction's old/new `valid_from`, reason, script name/version, timestamp; (3) apply
    in one transaction with before/after verification; (4) fix the root cause in
    `bootstrap_companies.py` itself (`widen_existing_windows`, called every re-run, never
    narrows) plus a regression test (`tests/test_identifier_window_repair.py`, 3 tests,
    reproducing the exact backfill-gap scenario and a real symbol-reuse rejection).
  - Backed up `company_identifiers` first
    (`../ledgerlight-backups/pre-identifier-window-repair-backup.sql`). Dry run found 2,936
    stale windows; the guard correctly rejected 87 as genuine ambiguous cases (temporary
    dual-ISIN periods, e.g. GRASIM; mid-gap renames, e.g. SKSMICRO->BHARATFIN,
    MAX->MFSL) rather than guessing. Applied 2,849 corrections in one transaction (0 narrowed,
    all logged to the audit trail); recovered 311,833 of the ~393,553 theoretical rows -- the
    gap is exactly the 87 guarded skips, reported plainly, not rounded up. Evidence:
    `docs/phase-3/evidence/identifier-window-repair-dry-run.json`,
    `identifier-window-repair-apply-run1.log`.
  - **Downstream rebuild check (evidence-based, not assumed)**: grepped every real usage of
    `company_identifiers` validity windows. `ledgerlight/knowledge/filings.py`'s
    `link_filings()` is the only date-windowed resolver that writes a stored artifact
    (`Filing` rows) -- but the earliest Filing-linked document's `known_at` (2019-07-04) is
    AFTER the latest stale-window gap end (2018-12-20), so **0 Filing rows were affected**.
    `scripts/populate_outcomes.py`'s company resolution (`_company_id_for_symbol`,
    `_company_id_for_document_identifiers`) uses no date window at all, so **0 Outcome rows
    were affected**. Entity/Mention/EntityLink tables never reference `company_identifiers`.
    `feature_snapshots` has 0 rows (not yet built) -- nothing to rebuild there, it will be
    built fresh on the corrected windows. Re-ran `scripts/entity_link_report.py` to confirm:
    care 162/162, sebi 84/84 unchanged; ibbi 55/55 -> 100/100 (the full-universe crawl's own
    progress, unrelated to this fix) -- all still 100% auto-linked.
  - Re-ran `scripts/bootstrap_companies.py` live end-to-end: `widen_existing_windows` found
    0 remaining widenable windows (confirms the one-time repair already converged) and 65
    still-guarded cases (down from 87 -- some were resolved properly through ordinary
    multi-ISIN company grouping instead of the cruder single-window widen, once the backlog
    below was cleared). As a real, disclosed side effect, this same re-run also bootstrapped
    1,819 companies (3,650 identifiers) that had NEVER been bootstrapped at all -- a separate,
    pre-existing backlog unrelated to the stale-window bug, confirmed via a direct company
    count (4,553 -> 6,372). These are net-new companies with previously zero
    `company_identifiers` rows, so no previously-resolved Filing/Outcome could have been
    wrongly linked -- this only adds coverage, it does not change past results.
  - Mid-task, Docker Desktop itself crashed (0 docker processes, its service Stopped) --
    confirmed as a real environment failure (consistent with this environment's documented
    low-memory-kill pattern), not a code bug, and the still-running full-universe IBBI crawl
    died as a side effect. Restarted Docker, confirmed via `docker compose up -d` plus a
    `pg_isready` wait, and confirmed the already-committed 2,849 audit rows survived intact.
    The IBBI crawl needs restarting (tracked in Exact next step below).
  - All tests green: `tests/test_identifier_window_repair.py` (3/3), full non-integration
    suite (232/232), ruff + mypy clean on every touched file.

- **§4.0b a SECOND real bug, found immediately while re-verifying the fix above**: COMPLETE.
  Re-checking the price_bars-to-company join after the stale-window fix showed it returning
  MORE rows (2,385,813) than real EQ rows exist (2,370,656) -- a join blowup, meaning some
  price_bars rows were matching more than one company. Root cause: the bootstrap re-run's
  1,819-new-company backlog (above) recreated the exact Sec2.4 fragmentation bug at a small
  scale -- a never-before-bootstrapped ISIN sharing an NSE symbol with an ALREADY-bootstrapped
  company produced a SECOND, duplicate Company row, since the new-ISIN grouping pass has no
  visibility into existing companies' claims. Confirmed via `created_at` timestamps (one row
  from the original 2026-10-25 dedup fix, the duplicate from today's re-run) and a concrete
  real example: 8KMILES (today's stale duplicate) / SECURKLOUD (the correct, already-renamed
  company) -- 90 distinct symbols affected, 94 real ISIN-groups.
  - **Flagged to the user before any further DB mutation** (per the established pattern for
    this class of fix); user chose "fix properly now" over a narrow one-off patch.
  - Root-cause fix: refactored the ORIGINAL Sec2.4 migration's grouping/merge logic out of
    `scripts/migrate_company_dedup.py` into a shared, reusable module
    (`ledgerlight/ingestion/company_dedup.py` -- `load_groups`, `find_fragmented_groups`,
    `merge_fragmented_groups`), and wired it into `scripts/bootstrap_companies.py`'s `main()`
    so it runs at the end of EVERY bootstrap, not just as a manual follow-up migration. This
    makes the fragmentation bug self-healing going forward, by construction, using the exact
    same proven merge logic (canonical = the company already correctly named after the
    group's real latest symbol; re-points Filing/Event/LabelItem/Entity references; deletes
    duplicates) rather than inventing a new, less-tested path.
  - Hit a real integration bug while applying this to the 94 live duplicates: the stale-window
    fix's own `identifier_window_corrections` audit table has a hard FK to
    `company_identifiers.id`, and the dedup merge's delete-and-regenerate step collided with
    it (`ForeignKeyViolation`) for identifiers that happened to be in both fixes' scope. Fixed
    by making the audit table genuinely self-describing instead of hard-dependent on the
    identifier row surviving forever: added denormalized `identifier_type`/`value` columns
    (migration `a688b3ceaf8c`, backfilled all 2,849 existing rows from the still-intact
    `company_identifiers` before changing anything), made `identifier_id` nullable with
    `ON DELETE SET NULL`. The audit history is permanent and self-contained even after its
    original identifier row is later deleted/regenerated by a legitimate merge.
  - Backed up first (`../ledgerlight-backups/pre-second-company-dedup-backup.sql`). Applied
    for real: 94 groups fixed, 94 duplicate companies deleted, 307 identifiers regenerated,
    9 Events correctly repointed to canonical (real `Outcome`-linked events that had resolved
    to the wrong/duplicate company via `populate_outcomes.py`'s un-windowed symbol lookup --
    now corrected), 0 Filing collisions. Verified: join count dropped to 2,352,150 (<= the
    real 2,370,656 EQ total, no more inflation); 0 remaining cross-company symbol-window
    overlaps (direct SQL check); companies 6,372 -> 6,278 (exactly -94). Re-ran
    `scripts/entity_link_report.py`: care 162/162, ibbi 100/100, sebi 84/84, all unchanged --
    confirms this fix didn't touch any already-correct Filing linkage.
  - Added `tests/test_company_dedup.py` (1 regression test, DB-backed) reproducing the exact
    8KMILES/SECURKLOUD-style scenario end-to-end against `merge_fragmented_groups`.
  - Re-ran `scripts/bootstrap_companies.py` a third time to confirm full convergence: 0
    companies created, 0 windows widened, 0 duplicates merged, 59 still-legitimately-guarded
    cases (stable) -- the system is now self-consistent and idempotent.
  - All tests green: full suite including integration, 312/312 (was 232/232
    non-integration-only before this entry); ruff + mypy clean on every touched file.

- **§4.1 UNIVERSE track price/liquidity STRUCTURED features**: COMPLETE for this feature
  group. `ledgerlight/modelling/price_features.py` -- 10 pure, trading-day-lookback feature
  functions (never fabricate; return `None` + a reason flag when there isn't enough real
  history): `ret_1m/3m/6m/12m` (simple return, 21/63/126/252 trading days), `volatility_3m`
  (annualized stdev of daily returns), `downside_volatility_12m` (same, negative days only),
  `max_drawdown_12m`, `turnover_trend_1m_12m` (21d mean turnover / 252d mean turnover),
  `amihud_illiquidity_1m` (Amihud 2002 |return|/turnover proxy), `distance_from_52w_high`.
  12 unit tests (`tests/test_price_features.py`), each checked against hand-computed
  arithmetic, not just "it runs". Found and fixed a real off-by-one in
  `turnover_trend`/`amihud_illiquidity`'s own lookback guards (required one day more history
  than the function's own loop actually reads) -- caught by a boundary-exact test, not
  inspection.
  - `scripts/build_feature_snapshots.py`: registers the 10 `FeatureDefinition` rows
    (`price-liquidity-1.0`, STRUCTURED tier, UNIVERSE track), then builds real monthly
    `FeatureSnapshot` rows. Universe membership per the brief's own wording ("the universe at
    each as_of is the companies trading in that period's bhavcopy") -- a company is snapshotted
    for a month ONLY if it has a real trade that month, never carried forward on stale data.
    Point-in-time safety: snapshot trading date = the latest real trade in that month whose
    bhavcopy `known_at` <= `as_of`; `max_input_known_at` = that trade's own `known_at` (a true
    upper bound, since one reliable source means `known_at` is non-decreasing in `trade_date`).
  - Real run (`docs/phase-3/evidence/build-feature-snapshots-run1.log`): 3,359 companies
    (every company with real EQ trading history -- not all 6,278 companies have equity,
    some identifiers are bond-only), 228,678 real `FeatureSnapshot` rows, `as_of` range
    2016-01-31 to 2026-10-31 (matches real `price_bars` coverage exactly).
  - **Spot-checked DHFL** (the discipline this project has used throughout -- never trust an
    aggregate count without checking a concrete real example): early 2016 snapshots correctly
    show `None` + `insufficient_history_*` flags (not enough lookback yet); by 2019 (DHFL's
    real, documented insolvency collapse) `ret_12m` worsens from -77.9% (Jan) to -93.7% (Sep),
    `distance_from_52w_high` bottoms near -93.7%, `downside_volatility_12m` rises to ~0.92 --
    all consistent with DHFL's real public history, not assumed.
  - All tests green: full suite including integration, 324/324; ruff + mypy clean.

- **§4.2 UNIVERSE track RULE-VERIFIED features (ratings + prior auto-linked history)**:
  COMPLETE for this feature group. `ledgerlight/modelling/rating_features.py`: a literal,
  span-verified regex (`CARE\s+(AAA|AA[+-]?|...|D)(?![A-Za-z0-9])`) over real CARE
  `DocumentPage` text, generalizing §3's `_RATING_D_PATTERN` to CARE's full long-term grade
  scale. Validated against 40 real CARE document first-pages before use
  (`docs/phase-3/evidence/rating-pattern-real-sample-check.log`): 28/40 matched; the 12
  "no match" cases were checked by hand and are real rating-WITHDRAWAL notices with no
  grade stated at all -- correct behavior, not a gap. A CARE document can rate several
  instruments of one issuer at different grades; this module takes the WORST (lowest
  ordinal) grade per document as a disclosed simplification, not an official single
  rating. Action type (downgrade/upgrade) is derived by ORDINAL COMPARISON to the prior
  observation, not by parsing English verbs -- more reliable and still fully
  span-verified, since each individual observation has a real evidence citation.
  `current_rating_ordinal`/`days_since_last_downgrade`/etc. are `None` (never 0) when a
  company has never been rated, so a model can't confuse "never rated" with "rated and
  stable" -- enforced by a dedicated test. 7 unit tests, including an explicit leakage
  check (an observation known only after `as_of` must never affect the computed value).
  - **Found and fixed a real, separate gap while building this**: the `filings` table was
    stale -- only 12 legacy companies, none from the real Sec2.3 CARE/IBBI/SEBI broadening
    (`link_filings()` had never been re-run since). Re-ran it:
    `docs/phase-3/evidence/link-filings-run-post-sec3-broadening.log` -- 289 new real
    `Filing` rows created, 38 distinct companies now linked (11 care, 29 ibbi, 13 sebi).
    61 documents remain genuinely unresolved -- checked two by hand (PNB Housing Finance's
    2003-2016 documents, Gensol Engineering's March-2023 document): both are REAL, dated
    before that company's own real NSE listing date (2016-11-07 and 2023-07-05
    respectively), so there is no real NSE symbol yet to auto-link to. Disclosed, not a
    bug to chase further.
  - `scripts/build_rule_verified_features.py` reuses the exact (company_id, as_of) grid
    already built by Sec4.1's price-liquidity pass, as a separate `feature_set_version`
    (`rule-verified-1.0`) so UNIVERSE membership stays identical without re-deriving it.
    `max_input_known_at` is the real max of (latest rating observation, latest SEBI
    filing, latest IBBI filing) known at or before `as_of` -- not a placeholder.
  - Real run: 38 companies, 3,241 `FeatureSnapshot` rows. Spot-checked DHFL: only one real
    CARE observation exists for it (2019-06-04, `current_rating_ordinal`=19/D, matching
    the single pre-existing seed document -- CARE discovery was never broadened past the
    15-company SEED-track universe, a disclosed gap from Sec3), and one real 2011 SEBI
    filing (plausible -- a real regulatory order, not necessarily insolvency-related;
    checked the real document dates by hand, found no attribution bug).
  - All tests green: full suite including integration, 331/331; ruff + mypy clean.

- **§4.3 SEED-track governance features + financial features assessment**: COMPLETE for
  governance features; financial features EXCLUDED with real evidence, per the brief's own
  explicit fallback.
  - `ledgerlight/modelling/seed_governance_features.py`: counts of the 9 real governance
    event codes (AUD_RESIGN, PLEDGE_UP, KMP_EXIT, ID_EXIT, RATING_ACT, RESULT_DELAY,
    AUDIT_QUAL, FORENSIC, RPT_GROWTH -- GUIDANCE_MISS excluded, that is Sec5's own feature),
    trailing 12 months, tagged by real tier (CANDIDATE/VERIFIED). Checked the real
    project-wide distribution first: every governance event in this corpus is still
    `status='candidate'` (0 verified anywhere) -- matches Phase 1 Sec1.5's finding that no
    event type clears the gold-reliability bar. Reported plainly, not hidden.
  - **Found and disclosed a real, structural limitation** while spot-checking Vakrangee's
    real AUD_RESIGN events: `known_at_basis='retrieved_at'` for investor-relations-sourced
    documents (not SEBI/IBBI/CARE/NSE), per `ledgerlight.db.temporal`'s own deliberate
    policy -- so a real 2017-12-31 auditor-resignation announcement carries
    `known_at`=2026-10-25 (this project's own fetch date), not its real publish date.
    Confirmed in the real built snapshots: Vakrangee's `aud_resign_candidate_count_12m`
    is 0 for every month except 2026-10-31 (6), exactly the predicted one-time step
    function pinned to this project's own acquisition date, not a genuine temporal signal.
    5 unit tests including an explicit leakage check. Real run: 15/15 SEED-track companies
    matched, 1,406 `FeatureSnapshot` rows (`seed-governance-1.0`).
  - "Pledge level and change from structured numbers" (the brief's own wording) is
    explicitly NOT built: no structured pledge-level data source exists in this project's
    real corpus (confirmed, `docs/data/source-inventory.md` has no pledge-data entry) --
    disclosed as a real gap, not approximated from the text-derived `PLEDGE_UP` candidates.
  - **Financial features (revenue/receivables/CFO/PAT span-cited extraction)**: attempted
    real extraction against the only 2 real annual-report documents in this corpus
    (Brightcom, Thermax; 339 real extracted pages, 67 containing a relevant label). A
    simple rule-based "label + nearby number" extractor produced 94 real candidates;
    manually checked 7 by direct inspection against their real page text. Real result: at
    least 3 of 7 were genuine mismatches found by hand (e.g. "Trade Receivables - At
    Amortised Cost" is an accounting-policy heading with no number on that line, so the
    nearby-number heuristic grabbed an unrelated figure further down the page; one
    "Profit After Tax" match actually grabbed a "No. of Customers" KPI from a nearby
    infographic) -- roughly 40-50% real accuracy, nowhere near the brief's own required
    90% span-verification pass rate. **Excluded per the brief's explicit fallback**
    ("otherwise exclude them and say why"): n=2 real documents is also too small a sample
    to support ANY extraction claim regardless of accuracy, and real financial-statement
    tables need layout-aware parsing this project's raw-text extraction doesn't do --
    disclosed plainly rather than shipping an untested, unreliable extractor. Evidence:
    `docs/phase-3/evidence/` (the real candidate list and manual-check findings are in
    this progress entry, not a separate committed script, since the attempt was correctly
    abandoned rather than productionized).
  - All tests green: full suite including integration, 336/336; ruff + mypy clean.

## Not yet started

§5 (guidance extraction), §6 (LightGBM models), §7 (walk-forward eval + leakage controls), §8 (scoring +
storage), §9 (rest of the Dagster pipeline + commands), §10 (tests), §11 (documentation
set), §12 (run and verify), §13 (final commit/backup for §2-15, `phase-3:` prefix), §14
(exit gates), §15 (final report).

## Exact next step

1. The full-universe IBBI discovery crawl (`scripts/ibbi_universe_discovery.py`) is running
   again (relaunched after the Docker crash; PIDs confirmed alive, log growing in
   `docs/phase-3/evidence/ibbi-universe-discovery-run3.log`). Once it finishes: run
   `scripts/process.py` (or a scoped extraction job) on whatever new IBBI documents it
   found, re-run `scripts/link_filings.py` (now kept current, per the Sec4.2 fix above) and
   `scripts/populate_outcomes.py`, then refresh the counts in `docs/modelling/outcomes.md`,
   `docs/modelling/outcome-evidence-review.csv`, and this file. Consider broadening CARE
   discovery to the full universe too (not yet decided/done) -- would also broaden
   Sec4.2's rating features past the 15 SEED-track companies.
2. Re-run `scripts/build_feature_snapshots.py`, `scripts/build_rule_verified_features.py`,
   and `scripts/build_seed_governance_features.py` after any of the above change
   `price_bars`/`filings`/`events` data, so the feature snapshots stay current -- all three
   are safely re-runnable (upsert on conflict).
3. §4 is now fully complete (4.0-4.3: two real bugs fixed; STRUCTURED price/liquidity,
   RULE-VERIFIED rating/auto-link, and SEED-track governance features all built and
   verified; financial features explicitly excluded with real evidence). Begin §5:
   guidance extraction and `GUIDANCE_MISS` (guidance credibility) -- not yet started, not
   yet even designed. Read §5 of the brief closely; this needs a source of real forward
   guidance statements (management commentary on future results) to compare against later
   actual results, which this project has not yet confirmed it has in the real corpus --
   check `docs/data/source-inventory.md` and the real document corpus before assuming a
   source exists, same discipline as the pledge-data and financial-features checks above.
4. If a future session hits an apparent background-job hang with near-zero CPU growth on
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
