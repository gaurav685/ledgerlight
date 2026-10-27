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
  (`python scripts/ingest.py care_discovery`).

## In progress

- **§2.1 bhavcopy backfill**: RUNNING IN BACKGROUND. Started
  `python scripts/backfill.py 2012-01-01 2026-10-28` (today's date) to both extend
  backward from the current earliest coverage (2017-01-05) toward the brief's 2012
  target, and forward from the current latest coverage (2025-09-22) to present. Real,
  previously-documented finding (`docs/data/source-inventory.md`): the archive was only
  spot-checked AVAILABLE from **2016-01**, with "the pre-2016 boundary not pinpointed" --
  this run will directly, honestly establish whatever the real earliest date is (expect
  many 404s before ~2016, which is informative, not an error) rather than assuming the
  brief's 2012 target is reachable.
  - **To check progress or resume**: the process may already have finished by the time
    you read this -- check `powershell -Command "Get-CimInstance Win32_Process | Where-Object {$_.CommandLine -like '*backfill.py*'}"`
    first. If nothing is running and no completion log exists under
    `docs/phase-3/evidence/backfill-2012-present*.log`, the job needs re-starting (same
    command). If a log exists but shows an incomplete date range, resume with
    `python scripts/backfill.py <day-after-last-successful-date> 2026-10-28` (or
    whatever "today" is at resume time) -- the underlying `run_bhavcopy_range` is
    idempotent per date (content-addressed), so re-running an overlapping range is safe,
    just slower than a precise resume.
  - Estimated duration at the documented 0.499 req/s throughput: ~3,700 business days
    (2012-2026) x ~2s/day ~= ~2 hours. Well under the brief's "~6 hours, else record
    progress and document resume" threshold, so this is expected to finish in one run,
    not needing an explicit resume -- but if it doesn't, the above is the real resume
    procedure, not a guess.

## Not yet started

§2.3 (SEBI/IBBI full history), §2.4 (entity-link reporting -- partly addressed in passing
by §2.2's name-driven discovery, but SEBI/IBBI/other sources still need their own linking
pass and report), §3 (outcome definitions, frozen before any training), §4 (point-in-time
features + migrations), §5 (guidance extraction), §6 (LightGBM models), §7 (walk-forward
eval + leakage controls), §8 (scoring + storage), §9 (rest of the Dagster pipeline +
commands), §10 (tests), §11 (documentation set), §12 (run and verify), §13 (final
commit/backup for §2-15, `phase-3:` prefix), §14 (exit gates), §15 (final report).

## Exact next step

1. Check on the bhavcopy backfill (see "in progress" above for the exact check command).
2. Begin §2.3: SEBI orders and IBBI public announcements, full available history. Current
   state: only the handful of individually hand-found SEBI/IBBI documents from Phase 0/1
   (`known_seed_items.py`). Same method as §2.2: check robots.txt, try the obvious
   listing/search pages, look for a real discovery mechanism (API or otherwise) by reading
   the page's own source rather than guessing a URL pattern -- and if nothing crawlable
   exists, report that honestly rather than fabricating a mechanism.
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
