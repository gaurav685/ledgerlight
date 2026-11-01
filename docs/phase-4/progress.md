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

## Not yet started

- §4 orchestration: the state machine itself
  (`ledgerlight/agent/state_machine.py`) tying budgets/tools/claims/render/verifier
  together -- PLAN -> GATHER -> TIMELINE -> DRAFT -> VERIFY -> REPAIR -> FINALISE,
  checkpointed via `InvestigationStep`, with the VERIFY<->REPAIR loop (remove failed
  claims, re-render, never substitute a new unsupported claim, <= max_repair_rounds).
- §6: Markdown + JSON dossier export (the content model itself -- sections/claim_id_map
  -- already exists via `ledgerlight.agent.render.RenderedDossier`).
- §7: the human review CLI (`dossier-review`), reason codes, append-only audit, the
  immutable-event-version feedback loop, seeded QC (`qc-seed`).
- §8: `agent-eval` across the 15 SEED-track + ~15 UNIVERSE-track companies.
- §9: the full adversarial/failure test suite (prompt injection, crash/resume,
  determinism, REPAIR-never-substitutes, etc.) -- no placeholder tests.
- §10: the 7 CLI commands and the 9 required docs.
- §11: run and verify (lint, typecheck, tests, migrations from empty, agent-eval,
  qc-seed + review-queue dry listing, dossier-export x2, pre-commit, full-history
  gitleaks).
- §12: final commit/backup.
- §13: exit gates.
- §14: final report, `docs/phase-4/phase-4-report.md`.

## Exact next step

Build `ledgerlight/agent/state_machine.py`: the real orchestration loop. Design already
settled (see this session's own reasoning): claims are persisted progressively during
TIMELINE/DRAFT (real `Claim` rows, so render_offline always has real claim IDs); a
`Dossier` row is persisted exactly once, at the end (FINALISE or the terminal
NEEDS_REVIEW), carrying the LAST real render (even on failure, for human review) --
never one per repair round. REPAIR removes failed claims from the active set (never
adds a replacement) and re-renders with the reduced set; the VERIFY<->REPAIR loop runs
at most `budget.max_repair_rounds` times. Resume-from-crash reads `Investigation.state`
(the next state to execute) and continues from there, re-deriving nothing already
persisted. PLAN's deterministic default plan and DRAFT's offline-template renderer
come first; the optional LLM paths (plan validation, LLM renderer) are gated on
`LLM_PROVIDER`/a key in `.env`, recording "not run" otherwise.

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
