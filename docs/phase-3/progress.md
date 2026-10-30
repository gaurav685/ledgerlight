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
- **§2.1 bhavcopy backfill**: COMPLETE (with a real interruption and two real findings
  along the way). The original `2012-01-01 2026-10-28` run was killed by a machine
  restart (which also took the local Docker stack down) before reaching its forward end,
  stuck at 2023-07-20 in `$TEMP/backfill_2012_present.log`. On resuming this session
  (2026-10-30): Docker Desktop and the Postgres/Garage containers were restarted
  (`docker compose --env-file .env -f infra/docker-compose.yml up -d`; both came back
  healthy with their existing volumes intact). Real findings:
  - **Earliest-date boundary now exhaustively confirmed, not just spot-checked**: zero
    successful fetches exist in the `documents` table for 2012-2015; direct `curl`
    spot-checks return 403 for 2012-06-15/2014-01-10 and 200 for 2016-06-01/2016-12-30.
    Real earliest date: **2016-01-01**. The brief's 2012 target is not reachable on this
    path -- a real source limit, not a gap to keep chasing.
  - **A real parsing-pipeline gap was found and fixed**: 2016-01-01 to 2017-01-04
    bhavcopy files were fetched into the document store by the interrupted run but never
    parsed into `price_bars` (a separate step, `ledgerlight.processing.price_loader`, not
    part of the fetch job). Fixed by running `scripts/process.py` (idempotent;
    `docs/phase-3/evidence/process-all-run1.log` -- this run also processes the ~350 new
    CARE/IBBI/SEBI PDFs from §2.2/§2.3 through page extraction for the first time, and
    was still finishing as of the last checkpoint this session -- **re-verify its
    completion and the real final `price_bars` min/max date before relying on full 2016+
    coverage**, using the query in "Exact next step" below.
  - **Forward extension completed cleanly**: `python scripts/backfill.py 2025-09-23
    2026-10-30` (run after the Docker stack was back up): 289 business days attempted,
    272 new files, 17 correctly-identified non-trading days, 0 errors, 0.501 req/s
    (`$TEMP/backfill_forward_ext.log`).

## Not yet started

§2.4 (entity-link reporting -- partly addressed in passing by §2.2/§2.3's name-driven
discovery, but a dedicated per-source linking report hasn't been written), §3 (outcome
definitions, frozen before any training), §4 (point-in-time features + migrations), §5
(guidance extraction), §6 (LightGBM models), §7 (walk-forward eval + leakage controls),
§8 (scoring + storage), §9 (rest of the Dagster pipeline + commands), §10 (tests), §11
(documentation set), §12 (run and verify), §13 (final commit/backup for §2-15,
`phase-3:` prefix), §14 (exit gates), §15 (final report).

## Exact next step

1. **Verify `scripts/process.py` (started 2026-10-30, see §2.1 above) has actually
   finished** -- check `powershell -Command "Get-CimInstance Win32_Process | Where-Object {$_.CommandLine -like '*scripts/process.py*'}"`;
   if it's still running, wait (it is idempotent and safe to just let finish, nothing
   else depends on blocking for it). Once done, confirm real final coverage:
   ```
   python -c "from sqlalchemy import select,func; from ledgerlight.config.settings import load_settings; from ledgerlight.db.session import make_session_factory; from ledgerlight.db.models import PriceBar; s=load_settings(); S=make_session_factory(s); 
   with S() as sess: print(sess.execute(select(func.min(PriceBar.trade_date), func.max(PriceBar.trade_date), func.count())).one())"
   ```
   Expect min close to 2016-01-01 and max close to 2026-10-30. If Docker isn't running
   when you read this, start it first: `"/c/Program Files/Docker/Docker/Docker Desktop.exe" &`,
   wait for `docker ps` to respond, then
   `docker compose --env-file .env -f infra/docker-compose.yml up -d`.
2. Begin §2.4: write the per-source (CARE/IBBI/SEBI) name/CIN-to-company link report the
   brief asks for -- §2.2/§2.3's discovery jobs already link by construction (every fetch
   carries `CompanyIdentifiers`), so this is mostly a reporting pass over what already
   exists in the `documents` table, not new linking logic. Or move to §3 (outcome
   definitions) if §2.4 is judged already substantially covered by §2.2/§2.3's own
   per-company match/unmatch reporting -- a judgement call to make explicitly, not skip
   silently.
   ICRA and CRISIL stay excluded (CRISIL by its own exclusion terms, per `docs/data/
   source-inventory.md`).

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
