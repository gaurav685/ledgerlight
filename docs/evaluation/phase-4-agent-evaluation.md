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

From the real §11 run (`docs/phase-4/evidence/sec11-07-agent-eval.log`),
60 real investigations (15 SEED + 15 UNIVERSE companies, 2 as_of dates
each):

```
Real investigations run: 60
Status breakdown (track:final_status -> count):
  SEED:FINALISED: 30
  UNIVERSE:FINALISED: 30
Total claims in final dossiers: 740
Total claims removed in REPAIR: 72
Per-check-type pass rate:
  citation_resolves: 743/812 (91.5%)
  date_in_span: 0/3 (0.0%)
  entailment: 146/146 (100.0%)
  name_in_span: 143/143 (100.0%)
  point_in_time: 146/146 (100.0%)
Unsupported-claim leakage into a final dossier: 0
Runtime seconds: p50=0.08 p95=9.05
Tool calls: p50=5.0 p95=5.0
LLM tokens: p50=0.0 p95=0.0
Cost USD: p50=0.0000 p95=0.0000
```

**All 60 real investigations reached FINALISED** -- none needed review
for this run (no budget exceeded, no verifier crash, no exhausted
REPAIR rounds). **Zero real unsupported-claim leakage** into any final
dossier, across all 60 -- the target the brief sets.

This is the SECOND real run of this evaluation. The first real run
surfaced two real verifier bugs (`docs/phase-4/progress.md`'s §9/§11
entries, commit `379fa27`): `timeline_entry` claims were not exempt
from the empty-evidence requirement despite being documented as such,
and `date_in_span` ran against metric/care_rating claims whose real
evidence span structurally cannot carry a date. Before the fix: 452
claims removed in REPAIR, citation_resolves at 62.3%. After: 72 claims
removed, citation_resolves at 91.5% -- both logs are preserved in
`docs/phase-4/evidence/` history (via git) for anyone wanting the
before/after.

**The remaining ~9% of citation_resolves failures are real and
disclosed, not a Phase 4 defect**: 69 of 127 real `event_fields` rows
(`field_name='order_document'`) carry a genuinely zero-length evidence
span (`char_start=char_end=0`) -- a real, pre-existing Phase 1-3
extraction characteristic (that field cites "the whole document", not
a specific quotable span). `get_evidence`/`verify_claim` correctly
refuse to treat a zero-length span as real, citable evidence; any
event claim relying solely on such a span fails as unsupported and is
removed in REPAIR, which is the real, intended "precision over
recall" behaviour this project has stated throughout, not a bug to
suppress.

**`date_in_span` at 0/3**: the only 3 event claims that got far enough
to run this check (most `event` claims failed earlier at
`citation_resolves`, for the same `order_document` reason above) each
cite an evidence span stating only an admission *status*
("petition was admitted", "admitted into CIRP") rather than the
specific date -- the real date for that same event is evidenced by a
separate, narrower `EventField` whose own span IS checked
independently. `ClaimVerificationResult.passed` requires every check
on every cited evidence item to pass, so a claim with one date-bearing
and one status-only evidence item fails overall on the status-only
item's missing date. A real, conservative design consequence (not
fixed here, consistent with this project's stated "a false pass is
worse than an unnecessary REPAIR" priority) -- disclosed rather than
loosened late in this phase.
