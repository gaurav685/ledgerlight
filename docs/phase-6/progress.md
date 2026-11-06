# Phase 6A Progress

Read `docs/phase-6/brief-6a.md` first (the complete, verbatim brief), then
this file, before resuming any session. Branch
`phase-6/integrated-validation-release`, created from Phase 5 HEAD
`9227f51`.

GIT POLICY: commit locally only. No remote, no push, no tags.
ABSOLUTE RESTRICTION: no AI attribution of any kind on any commit.

## Sections

- §0 Ground rules -- standing, applies throughout.
- §1 Preflight: consolidated evidence file -- **COMPLETE** (2026-11-05).
  Green baseline (408 default + 322 integration, one sequential pass, no
  memory kill -- resolves the open Phase 5 full-batch gate).
  `docs/phase-6/orchestrator-evidence.md` built with verbatim Phase 2-5
  evidence. All 5 stop conditions checked explicitly: none triggered.
  Commit: `66f7020`.
- §2 Low-memory stack profile + deferred e2e/ZAP runs -- **COMPLETE** (see
  below).
- §3 End-to-end pipeline test (ingestion -> dossier) -- **COMPLETE** (see
  below).
- §4 Regression suite -- **COMPLETE** (see below).
- §5 Backtest reproducibility and audits -- **COMPLETE (PARTIAL)** (see
  below; one real sub-step blocked by host memory, not code).
- §6 Consolidated evaluation report (pre-review) -- **COMPLETE** (see
  below).
- §7 Human review pack (build only, no reviewing) -- **COMPLETE** (see
  below).
- §8 Performance and reliability -- NOT STARTED.
- §9 Security and tenant re-validation -- NOT STARTED.
- §10 Cost per filing -- NOT STARTED.
- §11 Data-source compliance and licence review -- NOT STARTED.
- §12 Final documentation -- NOT STARTED.
- §13 Clean-install and reproducible-setup test -- NOT STARTED.
- §14 Production-readiness checklist -- NOT STARTED.
- §15 Release-gate status -- NOT STARTED.
- §16 Run and verify -- NOT STARTED.
- §17 Commit (local only) and backup -- ongoing throughout.
- §18 Human checkpoint and 6A exit gates -- NOT STARTED. **STOP here --
  do not begin Phase 6B.**

- §2 Low-memory stack profile + deferred e2e/ZAP runs -- **COMPLETE**
  (2026-11-05). `infra/docker-compose.e2e-lite.yml` built
  (per-service mem_limit/mem_reservation, tuned Postgres, worker gated
  behind a `with-worker` profile, DAGSTER_MAX_CONCURRENT_RUNS=1). Real idle
  memory measured (postgres 26MiB fresh vs 2.3GiB accumulated-cache;
  garage/api/web all under 150MiB). The full Playwright e2e suite
  (`frontend/e2e/full-e2e-lite.spec.ts`) built and run against the real
  stack -- **4/4 passed**: login, search, overview+as_of, timeline+tiers,
  evidence+highlighted span (direct nav -- see the real UI gap noted
  below), investigation creation through FINALISE, dossier view, review
  decision (as reviewer), watchlist+alert-rule creation, webhook
  registration+test delivery, alert visibility after `generate_alerts.py`,
  cross-tenant denial. Real memory under load measured (~550MB total across
  all 4 services, comfortably inside budget).

  **Found and fixed a real, significant bug** while building this: the
  frontend's CSP (`script-src 'self'`, no exception) blocked Next.js's own
  inline hydration scripts outright -- React never hydrated in any real
  browser, so every form (login included) silently fell back to a native,
  unintercepted HTML GET submission with credentials in the URL. The
  documented Next.js nonce-based fix was implemented and tested directly;
  it did not work in this exact Next.js 16.4.3 setup (confirmed: no `nonce`
  attribute ever appeared on Next's own inline scripts). Deployed the
  pragmatic, honestly-disclosed fix instead (`'unsafe-inline'`, no nonce
  source present) -- full writeup `docs/phase-6/evidence/
  sec02-csp-hydration-bug.md`; residual risk recorded in
  `docs/security/threat-model.md`; both gaps (the nonce fix not working,
  and the ZAP baseline still not run) tracked in `docs/release/
  release-gates.md`.

  **Found a second real gap** (documented, not fixed -- a real missing UI
  affordance, not a defect in anything that exists): no page in this
  frontend ever links a dossier/timeline entry to a document URL carrying
  `char_start`/`char_end` -- the document viewer supports rendering the
  highlighted span (reads them from its own `searchParams`), but nothing
  navigates there with them. Proven directly in the e2e test via direct
  navigation with a real evidence span pulled from the database.

  **ZAP baseline run** against the real e2e-lite stack (own Docker
  network, no sudo): 0 FAIL in both runs. First run: 6 WARN/62 PASS. Two
  real, easy findings fixed (`X-Powered-By` header disabled via
  `poweredByHeader: false`; a real `Permissions-Policy` header added,
  denying every browser feature this app uses none of) and confirmed
  gone in a second run: 4 WARN/64 PASS. Remaining 4 triaged as accepted
  (`docs/phase-6/evidence/sec02-zap-triage.md`) -- the CSP finding is
  the same already-disclosed `'unsafe-inline'` trade-off; the other 3
  are informational or real-but-low-value (Cross-Origin-Embedder-Policy,
  not applicable to an app with no cross-origin embeds). Full Playwright
  suite re-confirmed 4/4 passing after both header fixes.

  Real host memory was highly unstable throughout this work (swung
  0.29GB-3.26GB free from the user's own other applications), causing 2
  real Docker build kills along the way -- all recorded in
  `docs/phase-6/evidence/`. Commit: `dea2c0c` (main), plus a follow-up
  for the ZAP work and header fixes.

- §3 End-to-end pipeline test (ingestion -> dossier) -- **COMPLETE**
  (2026-11-05). `tests/test_e2e_pipeline.py` (automated, 2 tests) and
  `scripts/e2e_pipeline_demo.py` (standalone, reproducible CLI script) --
  both call the exact same real production functions every other
  `scripts/*.py` entrypoint calls: import-local, store-backfill, page
  processing, chunking, embedding, rules-baseline classification, real
  AUD_RESIGN extraction+verification, audit-firm entity bootstrap,
  `get_risk_score`, `run_investigation`, review-task routing, a real
  alert rule firing a signed webhook delivery, and a real API check.
  `test_full_pipeline_ingestion_to_dossier_citation_chain` passed,
  asserting the full provenance/known_at chain end to end (every claim's
  cited version/page/char-span resolves to the real stored page text).
  `test_full_pipeline_runs_twice_without_duplicating_anything` passed,
  proving idempotency via real row-count snapshots before/after a second
  run. Both pass together in one pytest invocation. Full default suite
  (408 tests) and the complete integration suite re-run clean afterward
  (no regression from this section's fixes). Evidence:
  `docs/phase-6/evidence/sec03-*.log`.

  **Found and fixed a real, significant, previously-undiscovered bug**
  while building this: `data/manifests/sources.yaml` never had a
  `manual:` entry, despite `ledgerlight/acquisition/import_local.py`
  always writing `source_id="manual"` for every manually-imported
  document. This meant `documents.source_id`'s foreign key to `sources`
  always failed for the documented manual-download workflow
  (`docs/data/manual-download-checklist.md`'s own 14 real BSE/NSE-blocked
  items) -- that workflow could never have actually completed, for this
  project's entire history, because this exact path had never been
  exercised end-to-end against a real database before. Fixed by adding a
  real, documented `manual:` entry (verdict `AVAILABLE_WITH_LIMITS`,
  verdict_reason naming this exact gap) and re-running
  `scripts/sources_sync.py` (confirmed via direct DB query:
  `manual | AVAILABLE_WITH_LIMITS | t`).

  Also fixed, found while building the test: two real schema mismatches
  in the test's own teardown SQL (`mentions`/`entity_links` keyed by
  `version_id`, not a nonexistent `event_field_id`; `webhook_deliveries`
  must be deleted before `alerts` due to its FK); two real NOT NULL gaps
  in the test's own fixture setup (`alert_rules.created_by`,
  `webhooks.created_by` both required, not optional) -- all test-side
  issues, not production bugs, fixed directly.

  **Found a real cross-test pollution regression** caused by the
  `webhook_deliveries`-before-`alerts` teardown bug above: before it was
  fixed, failed early attempts at this same test left real orphaned rows
  committed (a tenant+webhook at a fixed demo URL, five test companies,
  and -- via `scripts/e2e_pipeline_demo.py`'s own runs -- the first-ever
  global `entities` row for "KPMG", since `bootstrap_audit_firm_entities`
  creates that entity globally, not per-test, and this was genuinely the
  first time AUD_RESIGN extraction had ever run end-to-end in this
  project's history). These orphans broke two unrelated, previously
  passing tests in the full integration run
  (`test_generate_alerts.py::test_a_new_event_produces_one_real_alert_and_a_signed_webhook_delivery`
  -- a stray unmocked webhook call; `test_knowledge_pipeline_integration.py
  ::test_full_pipeline_on_small_real_subset_produces_events_fields_entities`
  -- expected a new KPMG entity, found the leftover one instead). Root
  cause confirmed by direct query (both orphan rows timestamped this
  session, both referencing only this session's own test documents).
  Manually deleted the identified orphan rows (tenant, 5 companies and
  all dependents, 3 extra orphaned webhooks, the 1 leftover KPMG entity
  and its 2 links). But the KPMG entity came back after the very next
  clean (passing) run of `test_e2e_pipeline.py` -- this was not just a
  one-time leftover from the earlier failed attempts, but a **real,
  structural bug in the test's own teardown**: `bootstrap_audit_firm_
  entities()` creates a brand-new `entities` row scoped globally, not
  per document version, and the teardown's `mentions`/`entity_links`
  cleanup (scoped by `version_id`) never reached the `entities` table at
  all -- so every single passing run of this test, forever, would have
  left a fresh orphan `entities` row behind, re-breaking
  `test_knowledge_pipeline_integration.py` and any other test that
  depends on the real count of audit-firm entities. Fixed properly this
  time: the teardown now also deletes any `entities` row this test's own
  mentions resolved to, scoped precisely (collected via the real
  `entity_links` rows before they're deleted, removed only once no
  `entity_links` reference them any more, so a real shared entity would
  never be touched). Verified: ran `test_e2e_pipeline.py` again after the
  fix, confirmed zero `entities` rows named "KPMG" remain afterward, then
  re-ran the full integration suite (split into 4 memory-safe batches,
  324 tests total) clean -- 0 failures (one `test_cross_tenant_idor.py`
  DNS-resolution flake on the first batch attempt, confirmed transient
  by an isolated re-run, unrelated to any change here). Full default
  suite (408 tests) also re-confirmed clean.

  This is still a real, disclosed limitation worth naming going forward:
  any global, non-version-scoped side effect (entity bootstrap; a
  non-tenant-scoped alert job) can leak across tests if a future test's
  teardown doesn't account for it the same way -- not something this
  phase's brief asked to re-architect project-wide, so noted here rather
  than generalised into a framework-level fixture.

  Commit: `c98ae2e`.

- §4 Regression suite -- **COMPLETE** (2026-11-06).
  `tests/test_regression_snapshots.py` (6 tests) checks real, already-
  persisted production data (never synthetic) against a golden fixture
  (`tests/fixtures/regression_snapshots.json`): extraction outputs and
  event tiers (VAKRANGEE's real audit_firm events), entity links (the
  real "Price Waterhouse & Co" audit_firm entity), feature values at a
  fixed as_of (VAKRANGEE, 2017-01-31, all 3 real feature_set_versions),
  score values for the frozen `primary-risk-lightgbm` v1.0 artifact
  (GENSOL, 2025-03-31), and a dossier Markdown hash from the real
  offline renderer (GENSOL's real FINALISED dossier at 2019-01-01).
  Which real subject was chosen and why is documented in
  `docs/phase-6/evidence/sec04-regression-snapshots.md`. All 6 pass.
  `scripts/update_regression_snapshots.py --confirm --reason "..."`
  regenerates the golden file from current data for the same frozen
  subjects (never picks new ones) -- tested: refuses without
  `--confirm`, and reproduces the current file's values exactly when
  nothing has really changed. `make test-regression` runs the suite.

  `scripts/test_pyramid_report.py` (`make test-pyramid`) runs the full
  pyramid (unit, integration, corpus, e2e, security) and prints counts
  per layer, batching the integration layer internally with memory-
  aware waits. Real result, found and disclosed while building and
  running it (`docs/phase-6/evidence/sec04-test-pyramid-report.log`):
  - unit: 408 passed, 0 failed.
  - integration: 330 passed, 0 failed (51 files, batched).
  - corpus: 1 passed, **1 failed** -- a real, pre-existing, disclosed
    finding, not a regression from this phase: 363 of 6226 real pages
    across 22 real IBBI PDFs (file mtimes 2026-10-31, before this
    session) now genuinely need OCR, where a prior run of this same
    test found zero. The test's own docstring calls this scenario
    "useful to know, not a bug." Left open -- out of this phase's
    scope to build real OCR integration for it.
  - The single automated script was itself killed twice by the
    harness's own external memory-pressure killer, right at the start
    of the integration layer, despite its own internal memory-aware
    wait (which can only see memory inside its own process, not
    prevent an external kill of the whole thing) -- a real, disclosed
    limitation of running one long-lived process on this host. Worked
    around by issuing the exact same batches as separate tool calls
    instead (zero kills that way); the script's own docstring now
    records this. The real counts above come from that successful run.
  Commit: `66469d8`.

- §5 Backtest reproducibility and audits -- **COMPLETE (PARTIAL)**
  (2026-11-06). Restored the most recent real backup into an isolated,
  disposable database (`ledgerlight_restore_drill`, via the exact same
  real function `scripts/restore_drill.py` already uses) -- never
  touched the live database. Full writeup:
  `docs/phase-6/evidence/sec05-backtest-reproducibility.md`.

  Outcomes-build re-run against the clean restore: **0 new rows** --
  a real, positive reproducibility proof. Features-build re-run: **
  BLOCKED** -- 2 real attempts, both killed by the harness's own
  external memory-pressure killer before any output was even logged
  (host free memory 0.53-2.0GB at the time, from the user's own other
  applications -- same real, recurring instability as elsewhere in
  this phase). Not a code defect: the existing 236,427 real
  `feature_snapshots` rows in the restore are row-count-identical to
  the live database, independently proving this step already
  completed once (in Phase 3). Left open for a future session with
  more headroom.

  Backtest run 3x against the clean restore: byte-for-byte identical
  across all 3 runs, and every real metric (LightGBM PR-AUC
  0.26666666666666666, Brier skill score -0.22073794369268818, n=144)
  matches `docs/phase-3/phase-3-report.md` exactly. The leakage/
  permutation/feature-shift/univariate audit (`scripts/
  leakage_check.py`) also reproduced every real number from Phase 3
  exactly (0 outcome-date violations, 0 embargo violations,
  label-permutation PR-AUC 0.24199627187104908, feature-shift PR-AUC
  0.349025974025974, `days_since_last_downgrade` flagged at 1.0). The
  point-in-time proof test passed against the clean restore;
  survivorship is unit-level and already covered by the default suite.
  `model_registry` artifact hashes and a real score's `outcome_spec_
  hash` confirmed identical between the restore and the live database.

  **Honest note, not claimed as fixed**: Phase 3's own report disclosed
  that two consecutive `backtest.py` runs once differed in Brier score
  only. This section's three runs were perfectly identical in every
  metric including Brier score -- recorded as an observation (it did
  not reproduce here), not as confirmation the earlier anomaly is gone.

  Drill database dropped at the end -- no second live copy left behind.
  Commit: `75f2387`.

- §6 Consolidated evaluation report (pre-review) -- **COMPLETE**
  (2026-11-06). `docs/evaluation/final-evaluation.md` built,
  consolidating every real evaluation result from Phases 2-5 plus this
  phase's own fresh §4/§5 re-confirmation, one section per the brief's
  own list, each tagged GOLD / SILVER-UNREVIEWED / PENDING_HUMAN_REVIEW
  with real support counts and CIs throughout -- nothing invented.
  Headline, stated plainly, not softened: classification rules
  macro-F1 0.635 [0.432, 1.000] on a thin n=14 gold test split;
  extraction/entity-resolution/retrieval remain silver-only, awaiting
  this phase's own §7 human review pack (PENDING_HUMAN_REVIEW, run in
  6B); agent-eval found 0 unsupported-claim leakage across 740 real
  claims; the risk model does **not** beat its own base rate with
  statistical confidence at the real available sample size (5 distinct
  positive events) -- carried forward unchanged from Phase 3.
  Commit: `eabc52f`.

- §7 Human review pack (build only, no reviewing) -- **COMPLETE**
  (2026-11-06). Built all 5 real review types -- tools only; nothing
  has actually been reviewed (that is explicitly Phase 6B's job):
  - **Field review** (`scripts/field_review.py`): ~30 real
    `EventField` values across event types, with cited span + context,
    decisions correct/wrong-value/unsupported/skip.
  - **Entity-pair review** (`scripts/entity_pair_review.py`): real
    (mention, candidate entity) pairs scored with the production fuzzy
    matcher. **Honest disclosure**: only 5 real pairs exist (target
    ~20) -- the real corpus is too thin, matching Phase 2's own
    already-disclosed finding; not padded with invented pairs.
  - **Retrieval review** (`scripts/retrieval_review.py`): 10 real
    silver queries x real top-10 hybrid-search results, relevant/
    not_relevant/skip.
  - **Outcome-evidence spot-check** (`scripts/outcome_evidence_review.py`):
    all 45 real primary-outcome events (IBBI admissions + rating
    downgrades) -- under the 60 threshold, so no stratification was
    needed; evidence-supports yes/no/unclear + date-correct yes/no.
  - **Dossier review** (`scripts/build_dossier_review_sample.py` +
    the existing `scripts/dossier_review.py`): staged 10 real dossiers
    (mixed SEED/UNIVERSE track, mixed real score where one exists) +
    3 seeded-QC flawed dossiers, unlabelled, into a manifest +
    separate answer-key file. Found and fixed a real gap: a plain
    FINALISED dossier has no `ReviewTask` by default, so the existing
    flow couldn't address it by `--task-id` -- now opens one
    (`reason_code="phase6a_sample_review"`) for each real sample item.
    Found and fixed a second real gap: `dossier_review.py show` always
    printed a `seeded_qc` warning, AND `list` always printed the raw
    `seeded_qc` field plus a `reason_code` that is itself literally
    the string `"seeded_qc"` for a seeded item -- either one alone
    would spoil the blind mix for a genuine human reviewer. Added
    `--blind` to both subcommands; verified by direct comparison that
    with `--blind`, `list`'s output no longer distinguishes the 3
    seeded items from the 10 real ones. Also found and closed 1 stray
    `ReviewTask` left open from an earlier exploratory seeding attempt
    (not part of the final 13-item sample) -- the real open queue now
    has exactly 10 + 3 = 13 tasks, matching the manifest precisely.
    The generated manifest and answer-key files are gitignored,
    local-only (unlike this project's other generated manifests,
    which are normally committed) -- either file's content is itself
    the answer to which items are seeded, so committing it would let
    anyone reading the repo see the answer before reviewing.

  All 4 file-backed types share `ledgerlight/review_pack/` (an
  append-only JSONL audit log with resume/skip/reviewer-name support,
  and a test-split-first deterministic sampler). Every type has both
  a `make` target and the equivalent `.venv\Scripts\python.exe`
  PowerShell command; `make review-progress` reports counts per type
  and per reviewer. `docs/phase-6/human-review-guide.md` has the
  order, time estimates (~4 hours total), decision rules with
  examples, and a one-page summary. `docs/release/release-gates.md`'s
  own long-standing gap on this is marked PARTIALLY CLOSED (tools
  exist; actual human review still pending, by design).

  Re-ran the full default suite (408 passed) plus the real
  review/qc_seed/review_queue/label_review integration tests (46
  passed) after this work -- no regression. Commit: (pending --
  committing next).

## Exact next step

§7 is fully done. Move to §8: performance and reliability (API load
test, ingestion/processing throughput, agent runtime p50/p95, and 5
failure-recovery drills with before/after evidence).

## Superseded: original §5 next-step note (kept for history)

The leakage/
permutation/feature-shift/survivorship audits plus the point-in-time
proof.

## Known starting context (from Phase 5)

- Real host memory pressure was a recurring, confirmed problem throughout
  Phase 5 (multiple real OOM kills, unrelated to this project's own Docker
  stack -- from the user's other running applications). §2's own low-memory
  stack profile work directly addresses this; sequence accordingly.
- Deferred from Phase 5 (`docs/release/release-gates.md`): the full
  Playwright e2e suite, the ZAP baseline, a single-batch full
  integration-test run. This brief's own "Deferred gates now due" list
  names the Playwright/ZAP pair plus human review types that don't exist
  yet, the outcome-evidence spot-check, 10-dossier human review, and
  GitHub Actions verification after a first push (the last one stays
  blocked on GIT POLICY -- no remote -- same as every prior phase).
- Two items carried over from Phase 4/5, still unresolved, not part of
  this brief: pushing a backup bundle to a remote (no remote configured);
  SpiceJet's control-group status (a human decision from Phase 3 §17.1).

## Pending items carried over (not part of this brief, flagged so they are not lost)

- Push a backup bundle to a git remote -- no remote configured; GIT POLICY
  unchanged.
- SpiceJet's control-group status -- unresolved human decision, Phase 3
  §17.1.
