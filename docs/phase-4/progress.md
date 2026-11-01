# Phase 4 Progress

Read `docs/phase-4/brief.md` first (the complete, verbatim brief), then this file, before
resuming any session. Branch: `phase-4/investigation-agent`, created from Phase 3's
completion commit `195a714`.

## Sections done

- **§1 PREFLIGHT (2026-11-01)**: branched `phase-4/investigation-agent` from `195a714`.
  Green baseline recorded: lint clean, typecheck clean (108 source files), 340 unit tests
  + 93 integration tests pass (`docs/phase-4/evidence/preflight-01..04-*.log`). Printed
  the required verbatim sections from `docs/phase-3/phase-3-report.md` (§5 hardening
  results and reliability tiers; outcome counts by year and distinct positive
  events/companies; fold table; metrics tables vs. B0 with intervals; calibration choice
  and reason; leakage/permutation/feature-shift/survivorship results; ablation; exit-gate
  checklist §19). Stop-condition check: leakage check PASSED (0 outcome-date/embargo
  violations), the deliberately-leaky synthetic feature WAS caught
  (`tests/test_leakage.py`), all 12 exit gates marked PASS (disclosed caveats, no FAIL).
  **No stop condition triggered -- cleared to proceed.**
- **Brief saved (2026-11-01)**: the complete Phase 4 brief (original §0-§2 + Part A +
  Part B, received across three user messages) saved verbatim to
  `docs/phase-4/brief.md` and committed.

- **§2 (2026-11-01)**: `ledgerlight/agent/models.py` -- `Investigation`,
  `InvestigationStep` (checkpointed, unique on investigation_id+step_no),
  `Claim` (payload + a real evidence-span list, same shape as `EventField`), `Dossier`
  (immutable, new row per version), `ReviewTask` (dossier-or-claim reference enforced by
  a CHECK constraint, seeded_qc flag), `ReviewDecisionAudit` (append-only). Also added
  `EventVersion` (not separately named in §2's table list, but required by §7's feedback
  loop) -- a disclosed design choice. Migration `a3e14b3deee1`, verified reversible.
- **§3 (2026-11-01)**: `ledgerlight/agent/tools.py` -- all 7 tools
  (`search_filings`, `get_evidence`, `get_events`, `get_entity_history`, `get_timeline`,
  `get_risk_score`, `get_outcomes_context`), each returning a real, frozen
  `ToolEnvelope[T]` (Pydantic, `untrusted: Literal[True]`), each filtering to
  `known_at <= as_of`. Real smoke test against DHFL found and fixed a real bug (a NULL
  bind parameter caused `psycopg.errors.AmbiguousParameter`; fixed with
  `CAST(:x AS TEXT)`). 14 real integration tests
  (`tests/test_agent_tools.py`), each building small controlled fixtures so the
  point-in-time filter is directly checkable.

- **§4 budgets/claims/render (2026-11-01)**: `ledgerlight/agent/budgets.py`
  (BudgetConfig/Usage, JSON round-trippable, BudgetExceeded). `ledgerlight/agent/claims.py`
  (builds real ClaimDraft objects from Sec3 tool envelopes; `risk_signal`/`limitation`
  claims are a disclosed exception to "every claim has a real evidence span", including
  the disclaimer itself as a real claim so "every sentence maps to a claim ID" holds with
  zero exemptions). `ledgerlight/agent/render.py` (the offline deterministic template
  renderer, real source citations with a real <=15-word excerpt, a real determinism
  test). The state-machine orchestration itself (PLAN/GATHER/TIMELINE/VERIFY-REPAIR loop)
  is still pending -- see "Not yet started".
- **§5 (2026-11-01)**: `ledgerlight/agent/nli.py` (real local DeBERTa entailment, reusing
  Phase 2's exact model + its TOKENIZERS_PARALLELISM fix). `ledgerlight/agent/verifier.py`
  (citation resolution, point-in-time, date-in-span with real DD/MM/YYYY-only parsing
  -- never MM/DD, crore/lakh-aware number checking, banned-language scan, contradiction
  detection). `ledgerlight/agent/nli_calibration.py` +
  `scripts/calibrate_nli_threshold.py`: real calibration against a SYNTHETIC labelled
  set -- every threshold 0.35-0.95 gives perfect precision/recall on that small set;
  `DEFAULT_NLI_ENTAILMENT_THRESHOLD` set to 0.95 (top of the plateau, chosen for
  precision over recall, consistent with this project's "inconclusive is acceptable"
  culture). Real output: `docs/agent/nli-calibration.json`.

- **§4 orchestration (2026-11-01)**: `ledgerlight/agent/state_machine.py` --
  `run_investigation` ties budgets/tools/claims/render/verifier together. Each state
  COMMITS (not just flushes) immediately after its checkpoint -- real crash-resume
  needs durable per-step commits, same lesson as Phase 3's `scripts/process.py`. Real
  smoke tests against DHFL/GENSOL found and fixed two real bugs: (1) the disclaimer's
  own fixed text legitimately uses "fraud" in a negating sense ("not proof of ...
  fraud"), which the banned-language scan wrongly flagged -- fixed by exempting the
  disclaimer section specifically (disclosed, documented in `verifier.py`); (2)
  `render_offline`'s claim ordering depended on DB retrieval order (created_at ties
  broken by random UUID), not real content -- a genuine determinism bug, fixed by
  sorting every section's claims by real content (known_at/text + full payload JSON
  tiebreaker). 5 new integration tests, including a real simulated-crash resume giving
  a byte-identical final dossier to an uninterrupted run. **§4 and §5 are both now
  functionally complete.**

- **§6 (2026-11-01)**: `ledgerlight/agent/export.py` -- `export_dossier_markdown` (8
  sections in fixed order, empty sections explicitly marked "None found."),
  `export_dossier_json` (round-trips `sections`/`claim_id_map`/status). 4 unit tests
  against hand-built real ORM-shaped objects (no DB write needed).
- **§7 routing/decisions/audit/feedback (2026-11-01)**: `ledgerlight/agent/review.py` --
  `REASON_CODES` (6 enumerated codes), `determine_routing` (checks conflicting_evidence,
  budget_exceeded/verification_failed from `final_status`, high_severity_finding,
  candidate_tier_majority, low_confidence_extraction via a real join to `event_fields`),
  `create_review_tasks`, `record_decision` (append-only `review_decisions_audit`),
  `apply_event_feedback` (new immutable `EventVersion` row, never mutates `events.status`
  in place). Fixed a real routing bug: `conflicting_evidence` was only checked as a
  fallback when no other reason had fired, so a real conflict could be silently missed
  behind e.g. `budget_exceeded` -- moved to an unconditional check. 10 integration tests
  (`tests/test_agent_review.py`), using the same `real_session`-with-manual-cleanup
  pattern as `test_agent_state_machine.py` for the committing functions.

  While designing `qc_seed.py`'s `unsupported_claim` seed (a claim with `evidence: []`),
  found and fixed a real scoping bug in `verify_claim`: the empty-evidence exemption
  checked only `if not claim.evidence`, with no check on `claim.claim_type` -- so an
  `event`/`timeline_entry`/`metric` claim with empty evidence would incorrectly pass as
  exempt, when only `risk_signal`/`limitation` are meant to be. Fixed with an explicit
  `EVIDENCE_EXEMPT_CLAIM_TYPES = frozenset({"risk_signal", "limitation"})` check; other
  claim types with empty evidence now correctly fail as "unsupported claim: {type} claim
  has no evidence span". Also found `check_number_in_span`/`check_name_in_span` were
  implemented and unit-tested but never actually called from `verify_claim` -- only
  `check_date_in_span` ran for a metric claim. Wired both in (numeric value+unit ->
  number check; string value with a non-numeric unit, e.g. `CARE_rating_symbol` -> name
  check). Verified safe against real data: `rating_features.py`'s `rating_symbol` and its
  evidence span share one regex capture group, so the real span text equals the real
  rating value; confirmed via a live GENSOL smoke test (still FINALISED, no regression).
  Also deleted `investigation_timestamp_claim` from `claims.py` -- dead code, defined but
  never called anywhere (confirmed via grep).

- **§7 qc-seed (2026-11-01)**: `ledgerlight/agent/qc_seed.py` -- `seed_flawed_dossier`
  runs one real investigation to completion, then injects exactly one deliberately
  flawed claim of a given flaw type (`wrong_date`, `wrong_number`, `missing_citation`,
  `unsupported_claim`) on top of its real, passed-verification claim set and re-renders
  through the real offline renderer -- the flaw reads as plausible prose, never
  hand-written boilerplate bypassing the renderer. Produces a NEW dossier version;
  dossier version 1 (the real, unflawed render) and `Investigation.final_status` (set
  by the real run before the flaw is ever injected) are both left untouched -- the one,
  documented exclusion rule §8's real statistics will rely on (filter on
  `ReviewTask.seeded_qc=True` and the dossier versions they reference). `seed_qc_batch`
  seeds a deterministic, configurable share of a target list, cycling through all four
  flaw types. `compute_catch_rate_report` reads real, decided-only `ReviewTask` rows
  with `seeded_qc=True` and compares the real recorded decision to that task's own real
  `expected_outcome` (always "reject" -- every seeded flaw is a genuine defect). Added
  `SEEDED_QC` to `review.py`'s `REASON_CODES`. 13 integration tests
  (`tests/test_agent_qc_seed.py`), including real evidence-span corruption for
  `wrong_date`/`wrong_number` (raises rather than fabricating a span when no real donor
  claim exists), batch fraction edge cases, and catch/miss/undecided scenarios.
  **§7 is now fully complete.**

- **§8 (2026-11-01)**: `ledgerlight/agent/eval.py` -- `seed_track_company_ids` resolves
  the real 15 SEED-track companies via real NSE_SYMBOL identifiers (same resolution as
  `scripts/build_seed_governance_features.py`). `universe_track_company_ids` is a real,
  query-derived ~15-company UNIVERSE-track selection: the brief's own suggested rule
  ("mix of high/low score percentiles") turned out not to be usable -- real scores
  (`scores` table) exist for only the 5-company verified-coverage universe, itself a
  subset of SEED -- so this uses real event-count instead (most-events companies
  outside SEED + enough zero-event companies to reach 15, tiebroken by `company_id`),
  disclosed in the module's own docstring rather than silently substituted. `run_one`
  runs one real investigation and reports `final_status`, claims actually referenced by
  the final dossier (via `claim_id_map`, not just "not failed"), claims removed in
  REPAIR, usage, and a real unsupported-claim-leakage check (target 0) scoped to claims
  the final dossier actually references. `compute_check_type_stats` aggregates real
  per-check-type pass rates; `run_evaluation` ties these together with a real p50/p95
  percentile helper and an explicit-override parameter (used by tests and later a CLI,
  since a full real 15+15x2 run is too slow for a test suite). Real smoke test against
  GENSOL and a real UNIVERSE-track company: both FINALISED, no leakage. 11 integration
  tests (`tests/test_agent_eval.py`). **§8's evaluation library is done** -- the actual
  full real evaluation run across all 30 companies happens at §11 ("run and verify"),
  not here, so its real output can be pasted into the final report once, not twice.

- **§9 (2026-11-01)**: `tests/test_agent_adversarial.py`, the dedicated adversarial/
  failure suite, covering every case the brief enumerates (several already had real
  coverage in `test_agent_verifier.py`/`test_agent_state_machine.py`, cross-referenced
  rather than duplicated -- see this file's own module docstring for the full map).
  While preparing and writing it, found and fixed THREE more real gaps beyond what §7's
  work had already surfaced:
  - `check_entailment` was implemented and calibrated but never actually called from
    `verify_claim`. Wired it in -- but NOT against the literal rendered "Findings"
    sentence: confirmed directly against the real local DeBERTa model that a real,
    correctly-supporting evidence span scores ~0.24 against that literal sentence
    (which embeds an ISO timestamp and tier jargon the model does not read as entailed
    prose) but ~0.99 against a minimal natural hypothesis like "An AUD_RESIGN event
    occurred." Added a separate, minimal hypothesis builder in `verifier.py` for this
    reason; factored the literal rendered sentences out of `render_offline` into
    `event_claim_sentence`/`care_rating_claim_sentence` anyway, for clarity/reuse.
  - `check_number_in_span`'s percent/percentage_points branch only checked whether a
    bare matching number appeared anywhere in the span -- never the span's own real
    unit wording, so "5 percentage points" would incorrectly validate a claimed 5
    percent. Fixed with unit-aware regex patterns.
  - `verifier.py`'s own docstring already claimed a verifier crash fails closed to
    NEEDS_REVIEW, but `state_machine.py` never implemented that catch. Added a
    try/except around the `verify_dossier` call.
  - `find_contradictions` ran inside `verify_dossier` and was returned in its own
    result, but nothing fed that back into a re-render -- the persisted dossier's
    "Conflicting evidence" section was always empty, and `determine_routing`'s
    `CONFLICTING_EVIDENCE` check could never actually fire. Added a `_render` helper in
    `state_machine.py` that always recomputes `find_contradictions` from the active
    claim set before every `render_offline` call (DRAFT, REPAIR, VERIFY's resume
    fallback).
  - Also discovered (not a bug, a real DB integrity guarantee): `event_fields.
    evidence_version_id` has a real foreign-key constraint, so a broken evidence
    reference can never be constructed this way for a real `Event` -- the
    REPAIR-non-substitution test forces its real verify failure differently (a real,
    resolving span whose own text just doesn't contain the claimed date).
  Full default+integration suite re-run clean after every fix (380 + 169 passed).
  **§9 is now fully complete.**

- **§10 CLI commands (2026-11-01)**: `scripts/investigate.py`, `investigate_batch.py`,
  `dossier_show.py`, `dossier_export.py`, `dossier_review.py`, `qc_seed.py`,
  `agent_eval.py` -- thin argparse CLIs over the already-built Sec3-Sec8 library
  modules. Added two small library helpers `review.list_open_tasks`/
  `review.get_task_dossier` the review CLI needed. Smoke-tested every command for
  real against real companies (GENSOL, CCAVENUE) end to end, including a full
  seed-QC-then-decide-then-catch-rate round trip. Found and fixed a real robustness
  gap: `seed_qc_batch` raised and aborted the WHOLE batch if one target had no real
  donor claim for its assigned flaw type -- added an `on_skip` callback so a batch
  degrades gracefully instead (the library itself still does no I/O; the CLI reports
  the skip). Also cleaned up real test-fixture pollution this session's own earlier
  work (and manual CLI smoke-testing) had left in the local dev DB -- one batch was
  actively corrupting `compute_catch_rate_report`'s global query and failing a real
  test; real companies and their real investigation rows were never touched.
- **§10 docs (2026-11-01)**: `docs/adr/0007-investigation-agent.md`,
  `docs/agent/{architecture,tools,verifier,review-workflow,security}.md`,
  `docs/evaluation/phase-4-agent-evaluation.md` (methodology only -- real results pending
  §11's full run), a new `docs/release/release-gates.md` gap for the brief's own
  deferred-to-Phase-6 human review requirement, and a Phase 4 status paragraph in
  README.md. **§10 is now fully complete.**

## Not yet started

- §11: run and verify (lint, typecheck, tests, migrations from empty, agent-eval,
  qc-seed + review-queue dry listing, dossier-export x2, pre-commit, full-history
  gitleaks).
- §12: final commit/backup.
- §13: exit gates.
- §14: final report, `docs/phase-4/phase-4-report.md`.

## Exact next step

§4 through §10 are all done. LLM plan validation / LLM renderer were NOT built -- no
`LLM_PROVIDER`/key is in `.env` in this environment, so per the brief's own instruction
this records "LLM renderer not run" rather than being built against nothing real to
test it with; revisit only if a real key is ever added. Next: §11 (run and verify --
including the one, full, real `agent-eval` run across all 30 companies, which also
fills in `docs/evaluation/phase-4-agent-evaluation.md`'s real results), §12
(commit/backup), §13 (exit gates), §14 (final report).

## Open defects / known limitations (not yet resolved)

- (carried forward from Phase 3, still real and relevant to Phase 4's dossiers):
  - No EVENT-CANDIDATE event type currently meets the reliability bar -- every dossier's
    "Findings" section must label CANDIDATE events as unverified, per the brief's own
    §0/§5/§6 requirements.
  - The Phase 3 risk model is statistically inconclusive (5 distinct pooled positive
    events on the verified-coverage universe). Every dossier's "Risk signals" section
    must carry the model-card limitations verbatim, including "statistically
    inconclusive."
  - SpiceJet's control-group status is still an open human decision (Phase 3 report
    §17.1) -- relevant if SpiceJet is among the seed companies `agent-eval` investigates.
  - `uv.lock` remains stale in this environment (`uv` not on PATH); new Phase 4
    dependencies (if any, e.g. for Mermaid docs -- none expected, since Mermaid is plain
    text) should be pip-installed into `.venv` the same way Phase 3's ML deps were.
