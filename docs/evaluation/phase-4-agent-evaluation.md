# Phase 4 Agent Evaluation

Methodology below; real results are pasted in once §11's full real
`agent-eval` run executes (`ledgerlight.agent.eval.run_evaluation`
across the real SEED+UNIVERSE selection) -- not written here from
expectation. Human review of at least 10 real dossiers, including the
seeded QC catch rate, is explicitly **deferred to Phase 6** per the
brief's own instruction (added to `docs/release/release-gates.md`).

## Real target selection

**SEED-track (15 companies)**: `ledgerlight.ingestion.seed_track`'s
real 15 companies, resolved to real `company_id`s via their real
`NSE_SYMBOL` identifiers (`ledgerlight.agent.eval.seed_track_company_ids`
-- the same resolution `scripts/build_seed_governance_features.py`
already uses).

**UNIVERSE-track (~15 companies)**: a real, query-derived selection
(`ledgerlight.agent.eval.universe_track_company_ids`), documented in
that module's own docstring. The brief's own suggested rule ("a mix of
high/low score percentiles") is not usable here: real scores (the
`scores` table) exist for only the 5-company verified-coverage
universe, itself a subset of SEED. This uses real event-count instead:
the 8 companies (outside SEED) with the most real governance events,
plus enough companies with zero real events (the real, common case) to
reach 15, tiebroken by `company_id` for reproducibility.

**as_of dates**: two fixed, documented dates applied to every target
company (`ledgerlight.agent.eval.DEFAULT_EVAL_AS_OF_DATES`:
2019-01-01 and 2023-01-01) -- not derived per-company, so every real
investigation is checked against the same real point-in-time boundary
twice.

30 companies x 2 as_of dates = 60 real investigations per full run.

## What is reported

- Real FINALISED vs NEEDS_REVIEW breakdown, by track, with the real
  `failure_reason` head (e.g. `budget_exceeded`, `verifier_crashed`,
  `verification_failed`) tallied per reason.
- Real claims actually referenced by each final dossier (via its own
  `claim_id_map`, not just "not marked failed") and real claims removed
  in REPAIR.
- Real per-check-type verification pass rate, aggregated across every
  real claim's own `verification_checks`.
- **Unsupported-claim leakage into a final dossier -- target 0.** Any
  real occurrence (a claim the final dossier actually references that
  has empty evidence and a non-exempt claim type) is reported as a
  DEFECT, never folded into a rate.
- Real runtime (wall seconds), tool calls, LLM tokens, and cost, p50/p95
  across all 60 real runs.

## Known, disclosed limitations carried into this evaluation

- The Phase 3 risk model is statistically inconclusive (5 distinct
  pooled positive events on the verified-coverage universe) -- every
  dossier's "Risk signals" section discloses this verbatim via the real
  model-card limitations text.
- No `EVENT`-CANDIDATE event type currently meets the reliability bar;
  every dossier's "Findings" section labels CANDIDATE events as
  unverified.
- `uv.lock` remains stale in this environment (`uv` not on PATH); this
  does not affect `agent-eval` itself (no new dependency was added for
  Phase 4 beyond what Phase 2/3 already installed into `.venv`).

## Real results

_Pending §11's full real run -- see `docs/phase-4/phase-4-report.md`
for the real pasted output once it exists._
