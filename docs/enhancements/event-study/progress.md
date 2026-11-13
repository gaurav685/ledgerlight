# Enhancement 1: Governance Event Study — progress log

Branch: `enhancement/event-study`, created from
`phase-6/integrated-validation-release` @ `0345a43` (2026-11-13).

Ground rules carried from Phase 6: commit locally only, no push, no
tags; no fabrication, no sudo, point-in-time integrity; neutral
language, not investment advice; no AI attribution on any commit.

## Status

- [x] §1 Pre-registration: `spec.md` + `spec.v1.json`, real sha256
      `74be99f7e34b2842066abf6466d3b12e8db06fec08705c035e526cbc67a69133`
      frozen in `model_registry` (`event-study-spec`/`v1`), freeze
      guard verified against a real tampered re-registration attempt.
      Commit `8762232`.
- [x] §2 core: migration (`event_study_runs`,
      `event_study_event_results`), `ledgerlight/research/event_study.py`
      (statistical core + DB orchestration), 29 tests (26 pure + 3
      integration). Commit `85e3308`.
- [x] §2 remaining: CLI (`scripts/event_study.py run|report`),
      Dagster `event_study_job` (manual-only, not scheduled), a real
      run against live data (run_id `473fb2e8-d5b9-48f8-97a7-19789bc33878`).
- [x] §3 Outputs: `report.md`, 3 real CAAR PNGs, `/v1/research/
      event-study` + `/v1/research/event-study/companies/{id}` +
      `/v1/research/event-study/caar/{type}.png`, company-page
      "Market reaction" panel, `/research/event-study` page.
- [ ] §4 Verify and commit (final pass: full test layers, pre-commit,
      gitleaks, print raw evidence, bundle).

## The real first run's own result, stated plainly

56 real primary events (SEBI orders 37-40 per window, CARE downgrades
11, CARE upgrades 3) after filters (120 raw -> 85 estimation-
sufficient -> 80 liquid -> 1 confounded -> 56 primary). **No (event
type, window, test) combination is statistically significant after
the real Holm-Bonferroni correction** -- every `*_p_holm` value is
1.0. Stated honestly, as the brief's own closing line requires: this
run found no significant market reaction it can report with
confidence.

A real, material, disclosed finding along the way: SEBI orders'
primary-window mean CAR (+35.6%) looked implausible until traced to
31 of 42 real primary events being flagged `possible_corporate_action`
(|daily return| > 50% somewhere in their own window) -- the median
(-3.5%) tells the real, more robust story. `report.md` now shows
both, plus a flagged-vs-clean mean breakdown per event type, so this
is never hidden behind a single misleading mean.

## Log

**2026-11-13** — Branch created, `brief.md` saved verbatim,
`progress.md` initialized. Dispatched a read-only research pass over
the existing schema (`price_bars`, `events`/outcome tables, any
`model_registry`, `Company`/`Filing` linkage, Alembic migration
convention, Dagster asset convention, CLI/API router conventions,
trading-calendar handling, and available stats/plotting
dependencies) to ground §1's spec in what actually exists, rather
than inventing table/column names. §1 work starts once that comes
back.

**2026-11-13 (cont.)** — §1 and §2-core done (commits `8762232`,
`85e3308`). Real findings worth remembering:
- **IBBI admissions are tier=CANDIDATE, not VERIFIED** (all 31 real
  rows, `status="candidate"`, "pending the brief's required human
  spot-check") -- conflicts with the brief's own "(auto-linked,
  verified)" framing for this event type. Resolved: IBBI is a
  secondary/exploratory arm, excluded from primary significance
  claims. SEBI orders (69 events) are genuinely VERIFIED and primary.
  CARE downgrades/upgrades bypass the tier system entirely (rule-
  extracted, span-verified, same as Phase 3's own model features) --
  also primary. Only 11 real companies have a CARE filing at all.
- **Autogenerate false positive**: `env.py`'s metadata import list is
  missing `ledgerlight.api.rate_limit` (a deliberately un-mapped
  table) and 4 real FKs lack an explicit `name=` from creation time --
  both cause spurious "drop" detections on ANY future autogenerate
  run in this repo, not just this one. Stripped by hand this time;
  flagged here as a real, pre-existing, out-of-scope gap for whoever
  next runs `alembic revision --autogenerate`.
- **`uv` is not available in this sandboxed tool environment** --
  `statsmodels`/`matplotlib` were installed directly into `.venv` via
  `pip` for real local dev/test use; `pyproject.toml`'s own
  `dependencies` list was updated, but `uv.lock` was NOT regenerated
  (no `uv` to run `uv lock`/`uv sync` with). The user should run
  `uv sync` once to reconcile the lockfile.
- **BMP/Corrado rank tests need real estimation-window dispersion**:
  a fully noiseless synthetic fixture (perfect for testing the plain
  OLS/AR arithmetic) makes both tests' own variance estimate exactly
  zero -- found while writing the test suite, not a bug in the
  formulas, fixed by using a small-deterministic-noise fixture
  specifically for those two tests.

**2026-11-13 (cont. 2)** — §2 finished, §3 built, the real first run
executed. Two more real bugs found running against real data for the
first time (never caught by the 29-test suite, since none of it
exercises a full real DB-backed run):
- **`NoReferencedTableError` on first real commit**: `EventStudyEventResult.
  company_id`'s FK to `companies.id` failed to resolve because no code
  path in `scripts/event_study.py`'s own process ever imported
  `ledgerlight.knowledge.models` (where `Company` lives) -- SQLAlchemy's
  `Base.metadata` only knows about a table once its owning module is
  actually imported somewhere in the running process. Fixed by
  importing `ledgerlight.knowledge.models` directly inside
  `ledgerlight/research/models.py` itself, so this module carries its
  own real dependency rather than relying on the caller to have
  imported it first.
- **Host memory kills (3 real, confirmed via task-notification "low on
  memory")**: `build_market_index`'s original implementation pulled
  every real `price_bars` row (millions) into Python to compute a
  ~1,400-row daily index. Rewrote it to aggregate server-side in SQL
  (`SUM(...)/SUM(...) GROUP BY trade_date`) -- same real result
  (verified directly: 1,411 real turnover-weighted index entries,
  matching sample values), a few thousand real bytes transferred
  instead of a few hundred real megabytes. The run completed cleanly
  after this fix.
