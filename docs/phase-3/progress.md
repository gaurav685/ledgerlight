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

- **§5 guidance extraction (`GUIDANCE_MISS`)**: ASSESSED, limits stated -- exit gate 5's
  own explicit fallback, user-approved before building anything ("verify before building").
  Searched all 4,759 real pages in the entire corpus (every document type, not just
  `investor_presentation`) for quantitative, management-stated, forward-looking guidance
  language. 64 raw keyword hits, 0 real matches: 58 are the unrelated ICAI "Guidance Note"
  auditing-standard phrase or generic CSR "career guidance" text; the other 6 are false
  positives from generic "we expect" phrasing (CARE's own analyst commentary, SEBI
  procedural language) -- each checked and cited by document/page/char-span in
  `docs/modelling/guidance-extraction-assessment.md`. No management-issued quantitative
  guidance statement exists anywhere in this project's real corpus, because Phase 0/1's
  compliant-source acquisition never targeted earnings-call transcripts or dedicated
  guidance press releases -- confirmed, not assumed (even the one real
  `investor_presentation` document was checked directly: 0 hits across its 13 pages).
  **No extraction machinery built** -- there is nothing real for it to run on; building it
  anyway would mean fabricating synthetic guidance or shipping code untestable against a
  single real case. Added to `docs/release/release-gates.md` as its own tracked gap.
  Evidence: `docs/phase-3/evidence/guidance-search-full-corpus.log`.
- **Point-in-time integrity proof (exit gate 4)**: DONE, both halves. Query:
  `docs/phase-3/evidence/point-in-time-proof.log` -- **100% of the 230,144 feature_snapshot
  rows with a real `max_input_known_at` satisfy `max_input_known_at <= as_of`, 0
  violations**, across all three built feature tiers (`price-liquidity-1.0` 228,678/228,678;
  `rule-verified-1.0` 1,464/1,464 with a real input, 1,777 correctly `NULL` for companies
  never rated/linked as of that month; `seed-governance-1.0` 2/2 with a real input, 1,404
  correctly `NULL`). Test: `tests/test_point_in_time_integrity.py` (asserts the same query's
  `violating` count is 0 for every `feature_set_version`) -- real regression caught in my
  own first draft of the summary script (a wrong column index inflated a bogus "1.36%"
  figure before I caught and fixed it; the real result is unambiguous: 100%, 0 violations).

- **§9 pipeline and commands (the unblocked parts) + §11 documentation set (the unblocked
  parts)**: COMPLETE for everything not dependent on §6/§7's blocked training work.
  - Real Dagster wiring: `outcomes_build_op` and `feature_snapshots_build_op` (the latter
    chaining all three real feature-build scripts), joined into
    `outcomes_and_features_build_job` -- the brief's own "outcomes -> feature_snapshots"
    asset chain, implemented as ops+job to match this codebase's existing convention for
    every other Phase 3 build step (care/ibbi/sebi discovery etc. are also ops+jobs, not
    bare `@dg.asset`s). Each op dynamically loads the real script's own `main()` (same
    technique this project's tests already use for `scripts/*.py`, which is deliberately
    not a package) -- no parallel reimplementation of the build logic.
  - **Proved the wiring for real, not just load-tested it**: ran
    `outcomes_and_features_build_job.execute_in_process()` end to end --
    `success: True`, 9m45s, and it genuinely re-ran all four underlying scripts
    idempotently (picked up 1 new real `SEVERE_DRAWDOWN` and 30 new real
    `BHAVCOPY_DISAPPEARANCE` rows from bhavcopy data that advanced since the last run,
    0 new `IBBI_CIRP_ADMISSION`/`RATING_DOWNGRADE_D` since no new CARE/IBBI documents have
    been extracted yet).
  - Makefile targets added: `backfill-universe`, `outcomes-build`, `features-build`,
    `outcomes-and-features-build`, `point-in-time-proof`. `guidance-extract`/
    `guidance-match` deliberately NOT wired -- §5 found nothing real for them to run
    against; documented inline in the Makefile rather than left unexplained.
  - Documentation set: `docs/modelling/features.md` (**generated** by
    `scripts/generate_features_doc.py` directly from the real `feature_definitions` table
    -- never hand-typed, can't drift), `docs/modelling/guidance.md` (the brief's own
    canonical filename, summarizing the real §5 assessment), `docs/modelling/
    data-quality.md` (consolidates every real coverage figure and disclosed caveat found
    so far; the IBBI full-universe coverage section is an explicit, named placeholder --
    "pending," not a guess -- to be filled per the user's condition 1 once the crawl ends),
    `docs/modelling/evaluation-protocol.md` (the real §7 methodology, designed but not yet
    executed -- states in advance, before any model is trained, that the current pooled
    primary-outcome positive count (34, pre-dedup) is close to or below the brief's own
    30-positive "inconclusive" floor, so a later inconclusive result can't be read as a
    post-hoc excuse), `docs/adr/0006-risk-modelling.md` (the real design decisions made so
    far, and the ones still pending), README phase-status section updated.
  - Still blocked (§6-§8's own remaining pieces: train-risk/backtest/leakage-check/
    ablation/score/model-card commands, `docs/modelling/model-card.md`,
    `docs/experiments/<id>.md`) -- these need a trained model, which needs the IBBI crawl
    to finish first, per the user's explicit condition.
  - All tests green: full suite including integration, 337/337; ruff + mypy clean.

- **§10 unit tests (the unblocked parts)**: COMPLETE for two real gaps found while
  checking which of the brief's required unit tests already existed vs. were only
  documented.
  - **Outcome rules and censoring**: the censoring policy was, until now, only described
    in `docs/modelling/outcomes.md` prose and the JSON spec -- not real, testable code.
    `ledgerlight/modelling/censoring.py` implements both rules
    (`unknown_trading_stop`, `end_of_window_observation`) for real. Found and fixed a real
    design bug while writing it: the first draft flagged a currently-trading company as
    "disappeared" just because its own last trade happened to equal the project's overall
    data coverage end -- confusing "most recent available data point" with "this company
    stopped trading." Fixed by requiring a REAL confirmed gap (>= 90 days between a
    company's own last trade and the overall coverage end) before `unknown_trading_stop`
    can fire at all; a plain end-of-coverage window still correctly censors under the
    separate `end_of_window_observation` reason. 6 unit tests, each a concrete real
    scenario (still-trading company; real early disappearance; before vs. after the
    disappearance cutoff; no trade history at all).
  - **The feature-policy guard** (§10's own explicit requirement: "the primary model
    rejects EVENT-CANDIDATE features"): `ledgerlight/modelling/feature_policy.py`'s
    `assert_primary_model_feature_policy` checks the real `feature_definitions` table
    (never a hardcoded tier-name guess) and raises if any requested `feature_set_version`
    is not STRUCTURED or RULE_VERIFIED. 3 integration tests against the REAL rows already
    built in this database: `price-liquidity-1.0`/`rule-verified-1.0` pass;
    `seed-governance-1.0` (the real EVENT_CANDIDATE tier from §4.3) is correctly rejected,
    including when mixed with an allowed tier. This exists now, before any training code,
    specifically so a future PRIMARY-model training script cannot accidentally include
    ablation-only features by forgetting the rule.
  - Still open from §10's list (all genuinely need a trained model/fold builder, blocked):
    the embargo/fold-construction test, the calibration-choice-rule test, `get_score`
    point-in-time behavior, the leakage tests (label-permutation, feature-shift, the
    deliberately-leaky-feature catch), the small-real-slice end-to-end integration test.
    GUIDANCE_MISS boundary tests: N/A, §5 concluded limits stated, nothing to test.
  - All tests green: full suite including integration, 346/346; ruff + mypy clean.

- **Full-universe IBBI crawl honestly stopped, outcomes rebuilt, two real detection bugs
  found and fixed (user's explicit condition 1)**: COMPLETE.
  - **Crawl stopped, not completed.** After ~3h42m of real elapsed run time (started
    15:22, stopped ~19:04), real throughput measurement showed only 72 distinct real
    company-name searches issued across the crawl's entire lifetime, against the real
    ~2,617-company target universe -- ~2.75%. The original 1.5-3 hour estimate was wrong
    by roughly two orders of magnitude; disclosed plainly, not hidden. Full coverage
    recorded in `docs/modelling/data-quality.md`'s dedicated IBBI section: 154 real IBBI
    documents (up from the 55-document SEED-track baseline), known_at 2017-08-17 to
    2026-10-25, 29 distinct companies with a real auto-linked Filing.
  - **Extraction**: `scripts/process.py` (the generic, full-corpus tool) was tried first
    and killed after ~100 minutes with 0 new pages committed -- found by reading
    `ledgerlight/processing/batch.py` that `run_process_all` has no intermediate commits,
    so a run touching the full 2,621-version corpus risks losing all progress if killed.
    Wrote `scripts/process_ibbi_backlog.py` instead: scoped to just the real 101
    unprocessed IBBI versions, committing after every single document. Real run: 93/101
    processed, 1,189 pages, 53 via OCR, 8 real `_process_pdf_worker` 120s timeouts on
    especially large scanned documents (disclosed, not silently dropped).
  - **Re-ran `link_filings.py`**: 53 new real `Filing` rows (38→71+ distinct linked
    companies). **Re-ran `populate_outcomes.py`**: `IBBI_CIRP_ADMISSION` naively jumped
    20→101 -- investigated by hand before trusting it (this project's standing
    discipline), and found two real, serious, previously-undetected detection bugs:
    1. **IBBI's per-company search returns every document mentioning a company** --
       petition filings, hearing/attendance sheets, and dismissal/withdrawal orders, not
       only genuine admissions. Caught concretely: "ABB India Limited" (a real, large,
       listed, never-insolvent company) showed up as an admission purely because its one
       discovered document is a Section 12A **withdrawal** order. 56% of the newly
       broadened companies (33/59) had only one real IBBI document on file, with no
       independent evidence of its real order type.
    2. A loose, non-directional "admitted...Petition" fix for (1) created a SECOND real
       false positive: matched "the Corporate Debtor...admitted its liability to make the
       payment of the three outstanding invoices. 11. The Petitioner..." -- the debtor
       admitting a DEBT, not the tribunal admitting the case. Fixed by requiring the
       strict, directional "Petition IS/WAS/STANDS admitted" form only.
    Real fix: `_ADMISSION_LANGUAGE_PATTERN` now requires genuine admission-confirming
    text (a declared moratorium, "CIRP was initiated", or the strict admitted-petition
    form) in at least one discovered document per case; cases with none are skipped
    entirely (64 real cases correctly excluded this way, printed by the script itself),
    never defaulted to "admitted". 6 regression tests encode the real checked cases
    (DHFL's genuine match; ABB's withdrawal correctly rejected; the debt-admission false
    positive correctly rejected; ABINFRA correctly falls back to its OTHER genuinely
    qualifying document once the bad one is excluded).
  - **Real final counts, before vs. after the full rebuild** (full evidence:
    `docs/phase-3/evidence/outcomes-before-ibbi-rebuild.log`,
    `outcomes-after-ibbi-rebuild-final.log`):

    | outcome_type | before | after |
    |---|---|---|
    | `PRIMARY_IBBI_ADMISSION` | 20 | **31** |
    | `PRIMARY_RATING_DOWNGRADE_D` | 14 | 14 (CARE discovery not broadened) |
    | `SECONDARY_SEVERE_DRAWDOWN` | 7,463 | 7,514 |
    | `SECONDARY_BHAVCOPY_DISAPPEARANCE` | 831 | 835 |
    | `SECONDARY_SEBI_ORDER` | 69 | 69 |

    `PRIMARY_IBBI_ADMISSION` by year (after): 2017:0, 2019:2, 2020:2, 2021:1, 2022:1,
    2023:9, 2024:10, 2025:3, 2026:3. Pooled `PRIMARY_DISTRESS` positives (distinct
    companies, `IBBI_CIRP_ADMISSION` ∪ `RATING_DOWNGRADE_D`): **31** -- right at the
    brief's own 30-positive inconclusive floor (already flagged in
    `docs/modelling/evaluation-protocol.md`, now with the real final number).
  - **Rebuilt affected feature snapshots**: `rule-verified-1.0` rebuilt (38→71 companies,
    3,241→6,316 rows) to pick up the new real Filing/outcome data. Re-ran the exit-gate-4
    point-in-time proof after the rebuild: still **100%, 0 violations**
    (`docs/phase-3/evidence/point-in-time-proof-post-ibbi-rebuild.log`).
  - Outcome DEFINITIONS stayed frozen throughout (same spec hash,
    `d879a2874d063b0025820ce52223e443b5b14d7c8746aa8d9e3117e4f3503e1b`) -- only the
    populated rows refreshed, per the user's explicit condition.
  - All tests green: full suite including integration, 352/352; ruff + mypy clean.

- **§6/§7 modelling layer, in progress (2026-10-31), per the user's newest condition
  (outcome-coverage restriction, honest distinct-event/company counting, sensitivity,
  no-peeking, inconclusive-is-acceptable)**:
  - `ledgerlight/modelling/coverage.py`: `compute_verified_coverage` -- the real,
    DB-computed (never hardcoded) intersection of companies with both a real IBBI Filing
    and a real CARE Filing. Real result: exactly 5 companies (DHFL, FRETAIL, GENSOL,
    JETAIRWAYS, SPICEJET), window `[2017-08-17, 2026-07-21]`. This is far smaller than
    the 15-company SEED-track set used elsewhere.
  - `ledgerlight/modelling/censoring.py`: added a third rule, `unverified_source_coverage`
    (checked first), so any as_of/forward-window outside the verified coverage window is
    censored, not labelled negative.
  - `ledgerlight/modelling/dataset.py`: `build_primary_outcome_dataset` -- the real
    labeled dataset restricted to the verified universe, with `outcome_types` now
    parametrized for the sensitivity split. Real smoke test: 243 total rows, 99 censored,
    144 labeled, 36 positive company-months, 4 distinct positive companies, 5 distinct
    positive events. (SpiceJet has 2 real raw outcome events but 0 labeled positives --
    confirmed correct, not a bug: both events fall after its own real trading-stop
    cutoff, so every window that could observe them is censored by
    `unknown_trading_stop` first.)
  - `ledgerlight/modelling/dates.py`: shared `add_months` (de-duplicated from three
    separate copies in censoring.py/folds.py/dataset.py).
  - `ledgerlight/modelling/folds.py`: `build_walk_forward_folds` -- expanding-window,
    yearly outer folds, 24-month (12mo horizon + 12mo embargo) train cutoff, per the
    already-frozen `docs/modelling/evaluation-protocol.md`. Real fold table: 2017-2019
    have zero training rows (too early in the expanding window); only 2021-2024 have any
    real train positives.
  - `ledgerlight/modelling/reporting.py`: `count_positives` (distinct events/companies,
    not just company-month rows) and `company_clustered_bootstrap` (company-level
    resampling), per the user's explicit condition.
  - `ledgerlight/modelling/models.py`: B0 (base rate), B1 (non-learned rating-distress
    rule), B2/B3 (logistic regression), and LightGBM with inner-fold-only hyperparameter
    + imbalance selection (`split_inner_validation`, `select_lightgbm_config`), the
    isotonic-only-if->=50-positives calibration rule, and SHAP TreeExplainer
    interpretability. Added `lightgbm`, `shap`, `pandas` as real dependencies (pip
    installed directly -- `uv` unavailable in this environment, `uv.lock` left stale).
  - `ledgerlight/modelling/metrics.py`: PR-AUC, ROC-AUC, precision@K, recall@alert-rate,
    Brier/BSS, ECE + reliability bins, lead time -- every metric returns `None` rather
    than a fabricated number when it cannot be honestly computed.
  - `ledgerlight/modelling/backtest.py`: `run_backtest` orchestrates all of the above per
    fold and pooled. Real pooled result: 5 distinct positive events (**inconclusive**,
    below the user's 30-event floor); no model beats the base rate (all pooled Brier
    skill scores negative) -- no predictive-skill claim is made.
  - `ledgerlight/modelling/sensitivity.py`: the user's explicit rating-only/IBBI-only
    sensitivity split. Real result: rating-default-only = 3 distinct events/3 companies;
    IBBI-only = 2 distinct events/2 companies (3+2=5, consistent with the combined
    PRIMARY count).
  - `ledgerlight/modelling/leakage.py`: outcome-date-after-as_of check (0 real
    violations), embargo-enforcement check (0 real violations), label-permutation
    (permuted pooled LightGBM PR-AUC 0.242, close to prevalence 0.25 -- consistent with
    the no-skill finding), feature-shift, and `univariate_pr_auc_flags`. Real, disclosed
    anomaly: the feature-shift test's pooled PR-AUC (0.349) is HIGHER than the real
    unshifted PR-AUC (0.267) -- the brief flags this case for investigation rather than
    silent acceptance. Likely cause (stated, not hidden): with only 4-5 distinct real
    events and the 12-month forward-window labeling producing long runs of consecutive
    positive company-months per event, a 1-month feature shift usually still lands inside
    the same distress episode rather than genuinely testing future information -- a real
    limitation of this check under this dataset's sparsity. The deliberately-leaky
    synthetic feature IS caught (`tests/test_leakage.py`, PR-AUC 1.0), proving the
    detection mechanism itself works. The univariate flag also catches a real feature,
    `days_since_last_downgrade`, at PR-AUC 1.0 in the real data -- disclosed for the final
    report, not necessarily proof of leakage given the tiny sample.
  - `ledgerlight/modelling/survivorship.py`: real, surprising finding -- ALL 5 companies
    in the verified-coverage universe have a real confirmed trading-stop gap before the
    current `price_bars` coverage end (2026-10-30), so the "without later-delisted
    companies" variant is empty. Not a bug: this restricted universe, by construction,
    consists only of companies with both real IBBI and CARE coverage, which in practice
    means companies that actually went through distress.
  - `ledgerlight/modelling/data_quality_report.py`: real missingness by feature and year
    (censored rows included in the denominator). Real finding: most price-liquidity
    features are 55-100% missing in 2023-2025 within this universe -- disclosed coverage
    degradation in the most recent years.
  - `ledgerlight/modelling/ablation.py`: arms (a) STRUCTURED, (b) +RULE-VERIFIED, (c)
    +EVENT-CANDIDATE (the real SEED-track `seed-governance-1.0` features, merged in as a
    deliberate, disclosed exception to the feature-policy guard for this one comparison).
    Real result: all three arms produce IDENTICAL pooled PR-AUC/BSS -- every fold's
    LightGBM selection falls back to the base-rate prevalence regardless of which features
    are offered. Per the brief's own instruction, reported plainly: (c) adds nothing
    measurable over (a) or (b) in this dataset.
  - **§7 is now functionally complete.** All new modules lint/format/mypy clean; full
    suite green (336 tests) after each commit.

- **§8-§11 complete (2026-10-31)**:
  - §8: migration `6d4589929764` adds `scores`/`experiments` tables (verified reversible).
    `ledgerlight/modelling/scoring.py`: `write_scores`, `get_score` (real integration test
    proves it never returns a future score), `record_experiment`, `write_experiment_doc`.
  - §9: `scripts/train_risk.py` (trains one final deployable LightGBM model on the full
    real labeled dataset, uploads to Garage, records in `model_registry` -- real run
    confirmed deterministic/idempotent: identical artifact_hash on a second run).
    `scripts/backtest.py` (records each run as an `experiments` row + auto-generates
    `docs/experiments/<id>.md`; real two-run test confirms "IDENTICAL... 0 diffs", proving
    §9's reproducibility requirement). `scripts/leakage_check.py`, `scripts/ablation.py`,
    `scripts/score.py` (loads the trained artifact from Garage; two deployment-time
    simplifications disclosed in its own docstring -- 0.0 imputation and
    calibrated==raw_probability, since neither training medians nor the per-fold
    calibration map were persisted), `scripts/model_card.py`. Makefile targets added.
    Dagster: `train_risk_op`/`risk_train_job` (manual only), `score_op` -> `reports_op` /
    `risk_score_and_report_job` with a monthly cron schedule -- `dagster definitions
    validate` passes.
  - §10: `tests/test_end_to_end_risk_pipeline.py` runs coverage -> dataset -> folds ->
    backtest -> leakage-check -> write_scores/get_score against the real DB in one test,
    using the real 5-company universe itself as the "small real slice". All other §10
    items were already covered by earlier commits (embargo/fold, calibration-rule,
    get_score, leakage tests).
  - §11: `docs/modelling/model-card.md` generated directly from the real pipeline
    (intended use, data/outcomes/metrics with company-clustered bootstrap intervals,
    calibration, coverage limits, failure modes, ethical considerations -- including the
    disclosed SpiceJet control-group concern). `docs/experiments/<id>.md` auto-generated.
    `docs/release/release-gates.md` and `README.md` updated with the real, inconclusive
    Sec6-10 result.

## PHASE 3 COMPLETE (2026-10-31)

§12 (run and verify), §13 (final commit/backup), §14 (exit gates re-marked), §15 (final
report) are all done. See `docs/phase-3/phase-3-report.md` for the full report. Headline
real result: the verified-coverage universe is 5 companies / 5 distinct positive events
-- statistically inconclusive, no model beats the base rate, stated plainly throughout.
**Per the user's explicit instruction, Phase 4 is NOT begun.**

## Not yet started (deferred beyond Phase 3, see the final report §17)

Human review of `docs/modelling/outcome-evidence-review.csv`; SpiceJet's control-group
status decision; whether to broaden CARE discovery to the full universe; whether to
persist training-time feature medians and the per-fold calibration map with the deployed
artifact; further investigation of the small backtest Brier-score reproducibility
anomaly (§16/§11 of the final report).

## Exact next step (for a future phase only -- NOT to be started in this session)

1. **§6-§11 are now complete** (coverage restriction, censoring, dataset, folds,
   B0-B3+LightGBM+calibration+SHAP, metrics, backtest, sensitivity split, leakage checks,
   survivorship, data-quality report, ablation arms, scores/experiments storage, all §9
   CLI commands + Dagster wiring, the end-to-end integration test, model-card.md and
   docs/experiments/<id>.md -- see above). Next: §12 run and verify (the full raw-output
   command sequence: lint, typecheck, all tests, migrations from empty, hardening eval,
   backfill-universe, outcomes-build, features-build, backtest, leakage-check, ablation,
   score, model-card, pre-commit, gitleaks), then §13 final commit/backup, §14 re-mark all
   exit gates with evidence, §15 final report.
3. Note the real pooled positive count under the verified-coverage restriction is just 5
   distinct events (far below the unrestricted-universe count of 31 noted in the §3 entry
   above, and below the brief's own 30-event floor) -- already reported as inconclusive
   in the real backtest smoke test; this is not a new finding to re-discover, just to
   carry through §7's remaining pieces, §8-§15, and the final report honestly.
4. Consider broadening CARE discovery to the full universe too (not yet decided/done) --
   would also broaden §4.2's rating features and `RATING_DOWNGRADE_D` past the 15
   SEED-track companies; currently still SEED-track-only.
5. Re-run `scripts/build_feature_snapshots.py`, `scripts/build_rule_verified_features.py`,
   and `scripts/build_seed_governance_features.py` after any further change to
   `price_bars`/`filings`/`events` data, so the feature snapshots stay current -- all
   three are safely re-runnable (upsert on conflict).
6. If a future session hits an apparent background-job hang with near-zero CPU growth on
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
