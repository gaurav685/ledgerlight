# Final Evaluation (Phase 6A §6 — pre-review)

Consolidates every real evaluation result produced across Phases 2-5
and this phase's own §5 reproducibility work into one place, each
section marked with its real evidence tier:

- **GOLD** -- evaluated against human-reviewed labels.
- **SILVER-UNREVIEWED** -- evaluated against silver (model/rule-derived,
  not yet human-reviewed) labels, or deterministic/structural checks
  that don't require human labels but also aren't gold accuracy
  numbers.
- **SYNTHETIC** -- evaluated against a synthetic fixture, not real
  corpus data.
- **PENDING_HUMAN_REVIEW** -- the real human review pack this phase's
  own §7 builds (not yet run by a human; running it is Phase 6B's own
  job, explicitly deferred per this brief).

All support counts and confidence intervals below are reproduced
verbatim from their cited source reports and this session's own fresh
re-runs (§1, §4, §5) -- nothing here is invented or rounded beyond
what the source already reported.

## 1. Classification

**Tier: GOLD** (test split, n=14) + **SILVER-UNREVIEWED** context
(validation, n=112; silver error rate, n=77 reviewed).

Source: `docs/phase-2/phase-2-report.md` §19.2-§19.3, verbatim-quoted
in `docs/phase-6/orchestrator-evidence.md`.

Frozen TEST split (n=14, never used for tuning, reported once):

| classifier | label | precision | recall | F1 | support | F1 95% CI |
|---|---|---|---|---|---|---|
| rules | AUD_RESIGN | 1.000 | 1.000 | 1.000 | 4 | [1.000, 1.000] |
| rules | PLEDGE_UP | 0.500 | 1.000 | 0.667 | 1 | [0.000, 1.000] (n<3) |
| rules | none | 1.000 | 0.778 | 0.875 | 9 | [0.625, 1.000] |
| rules | **macro F1** | | | **0.635** | | [0.432, 1.000] |
| tfidf_lr | AUD_RESIGN | 0.000 | 0.000 | 0.000 | 4 | [0.000, 0.000] |
| tfidf_lr | **macro F1** | | | **0.283** | | [0.111, 0.544] |
| deberta_zero_shot | AUD_RESIGN | 1.000 | 1.000 | 1.000 | 4 | [1.000, 1.000] |
| deberta_zero_shot | **macro F1** | | | **0.472** | | [0.417, 1.000] |

Production classifier is `rules_baseline` (selected via the full
111-item validation split, not this thin n=14/n=41 gold-only slice --
selection reasoning in the source, not re-derived here).

Silver-label error rate (n=77 human-reviewed decided items, bootstrap
95% CI, 10,000 resamples, seed 42): **overall 0.351** [0.247, 0.455].
Several per-class rates (`RPT_GROWTH` 0.667, `ID_EXIT` 0.833) have wide
CIs or insufficient support (n<5) -- not a precision claim at the
class level, context only.

## 2. Extraction

**Tier: SILVER-UNREVIEWED.** No human-reviewed gold field labels exist
yet; the human field review this phase's own §7 builds
(`docs/phase-6/human-review-guide.md`, ~30 fields) is
**PENDING_HUMAN_REVIEW**, to be run in Phase 6B.

- Phase 2 (`docs/phase-2/phase-2-report.md` §7d): 4 events, 7 fields, 0
  failed verifications against the real corpus at that time. Exact/
  normalized-match and coverage metrics against gold fields: not
  computed (no gold labels existed).
- Phase 3 hardening (`docs/phase-6/orchestrator-evidence.md`, Phase 3
  section): no event type meets the production reliability bar
  (support >= 10 AND lower-CI precision >= 0.7) on gold validation
  data; `AUD_RESIGN`'s hardening was directly informed by all 4
  TEST-split accepted examples, honestly disclosed and correctly
  labelled "test split consulted during development -- not held-out"
  (not a held-out gold result).
- This session's own golden-snapshot regression fixture (§4,
  `docs/phase-6/evidence/sec04-regression-snapshots.md`): 6 real
  `audit_firm` `event_fields` for VAKRANGEE, all `validation_status =
  validated`, re-confirmed byte-identical on every re-run -- a
  reproducibility proof, not an accuracy proof (nothing here says
  whether "Price Waterhouse & Co Chartered Accountants LLP" is the
  *correct* firm per a human reviewer, only that the pipeline
  reproduces its own answer).
- This phase's own §3 end-to-end test
  (`docs/phase-6/evidence/sec03-*.log`): a real, fresh document (KPMG
  resignation notice) correctly classified `AUD_RESIGN` and correctly
  extracted `audit_firm = KPMG`, `validation_status = validated`, 2/2
  runs -- another reproducibility/correctness-on-a-known-answer proof,
  not a gold accuracy metric over a labelled population.

## 3. Entity resolution

**Tier: SILVER-UNREVIEWED.** The human entity-pair review this
phase's own §7 builds (~20 pairs) is **PENDING_HUMAN_REVIEW**.

Source: `docs/phase-2/phase-2-report.md` §7e. Real bootstrap run: 12
company entities, 1 `audit_firm` entity ("Price Waterhouse & Co
Chartered Accountants LLP"), 3 mentions, all 3 correctly resolved (2
`normalized_name` auto-links, 1 `manual` first-seen bootstrap).
Pairwise P/R/F1 against exact-match-only: **not run** -- no labelled
mention-pairs exist, and the real corpus's entity surface was too thin
(effectively one audit firm, 12 companies with no observed real name
variants) to build a meaningful pair set without inventing cases.

Re-confirmed unchanged by this session's §4/§5 work: the same entity
(`25fc33c3-...`), same 3 links, same methods/scores, reproduced exactly
from a clean database restore (§5).

## 4. Retrieval

**Tier: SILVER-UNREVIEWED** (30-query silver set). The human retrieval
review this phase's own §7 builds (~10 queries x top-10) is
**PENDING_HUMAN_REVIEW**.

Source: `docs/phase-2/phase-2-report.md` §7f.

| method | n | recall@5 | recall@10 | MRR |
|---|---|---|---|---|
| lexical_bm25 | 30 | 0.567 | 0.667 | 0.330 |
| vector | 30 | 0.333 | 0.467 | 0.210 |
| hybrid_rrf | 30 | 0.533 | 0.633 | 0.258 |

Lexical BM25 wins outright over both vector and the hybrid RRF
combination -- reported honestly even though the hybrid approach isn't
best; see `docs/knowledge/retrieval.md` for that discussion. These are
silver-query labels (not yet human-reviewed), so the absolute numbers
should be read as directional, not a certified accuracy figure.

## 5. Citation and verifier (adversarial + agent-eval)

**Tier: SILVER-UNREVIEWED** for the agent-eval population numbers
(real investigations, not human-graded); the adversarial suite is
deterministic correctness testing against known-bad/known-good inputs
(closer to **GOLD** in the sense that each case's correct answer is
constructed and known by design, not inferred).

**Adversarial suite** (`docs/phase-6/orchestrator-evidence.md`, Phase
4 section): 14/14 passed, including a wrong-date rating claim and a
wrong `timeline_entry` both genuinely failing verification (not
silently passing), a mocked LLM output missing a claim ID caught, a
mocked LLM output introducing an unsupported new number caught, and a
prompt-injected document not affecting a real investigation's output.
Re-confirmed fresh this session (`sec01-verifier-wrongdate-tests.log`):
4/4 of the wrong-date/wrong-timeline-entry regression tests still pass.

**Agent-eval** (`docs/phase-4/phase-4-report.md` §6, 60 real
investigations: 15 SEED companies x 2 as_of dates + 15 UNIVERSE
companies x 2 as_of dates):

```
Status breakdown: SEED:FINALISED 30, UNIVERSE:FINALISED 30
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
```

The `date_in_span` 0/3 pass rate is a real, disclosed weak spot (small
support, n=3) -- not hidden here. **Zero unsupported-claim leakage**
into any final dossier across all 740 claims is the single strongest
real correctness result in this evaluation: every claim that survived
to a FINALISED dossier is evidence-backed.

**Seeded QC catch rate** (synthetic defects seeded into otherwise real
dossiers, to test whether the review pipeline catches them):

```
wrong_number       seeded=1 reviewed=1 caught=1 rate=100.0%
missing_citation   seeded=1 reviewed=1 caught=1 rate=100.0%
wrong_date         seeded=0 reviewed=0 caught=0 rate=n/a (no decisions yet)
unsupported_claim  seeded=0 reviewed=0 caught=0 rate=n/a (no decisions yet)
```

Human review of the 10-dossier sample (including seeded QC decisions)
is **PENDING_HUMAN_REVIEW**, built by this phase's own §7, run in
Phase 6B.

## 6. Risk model (backtest)

**Honest scope, stated plainly: this is an evaluation framework run
on a 5-company verified-coverage sample (144 company-months, 5
distress events); no demonstrated predictive skill; results
inconclusive.** This is never a market-wide prediction tool -- it has
not been shown to generalise beyond this small, hindsight-selected
sample of already-famous distress cases.

**Tier: SILVER-UNREVIEWED** / **INCONCLUSIVE** by the backtest's own
explicit statistical threshold (fewer than 30 distinct positive
events). Not a gold result -- there is no human-labelled "correct
risk score" to grade against; this is a real backtest against real,
verified-coverage outcomes.

Source: `docs/phase-3/phase-3-report.md` §9/§11, independently
reproduced three times from a clean database restore this phase
(§5, `docs/phase-6/evidence/sec05-backtest-reproducibility.md`) --
every number below matched exactly, byte-for-byte, across all three
re-runs and against the original Phase 3 report.

| model | PR-AUC | ROC-AUC | Brier skill score | n |
|---|---|---|---|---|
| B0_base_rate | 0.275 | 0.546 | -0.213 | 144 |
| B1_rating_rule | 0.354 | 0.634 | -0.296 | 144 |
| B2_price_liquidity | 0.444 | 0.574 | -0.209 | 144 |
| B3_structured_rule_verified | 0.237 | 0.523 | -0.867 | 144 |
| **LightGBM (primary)** | **0.267** | **0.542** | **-0.221** | 144 |

Pooled distinct positive events: **5** (DHFL x2, Future Retail x1,
Gensol x1, Jet Airways x1), distinct positive companies: 4 --
**INCONCLUSIVE** per the backtest's own stated bar (< 30 distinct
events). Company-clustered bootstrap 95% CI (LightGBM): PR-AUC 0.267
[0.099, 0.649]; Brier skill score -0.221 [-0.568, 0.338] -- the
interval straddles both positive and negative BSS. Calibration:
badly miscalibrated in the majority bin (108/144 rows predicted ~0,
real actual positive rate 22.2%).

The 5th verified-coverage company, SpiceJet, was originally picked
(Phase 0) as a "no known distress" control, not a positive case; a
later search found 8 real NCLT insolvency *petitions* filed against
it (2021-2026) -- petitions, not admissions -- which calls its
control-group status into question. Not resolved unilaterally;
flagged for human decision (`docs/phase-3/progress.md`,
`docs/release/release-gates.md`).

Leakage/permutation/feature-shift audit, also exactly reproduced:

```
outcome-date-after-as_of violations: 0
embargo violations: 0
label-permutation pooled LightGBM PR-AUC: 0.24199627187104908
feature-shift pooled LightGBM PR-AUC: 0.349025974025974
univariate PR-AUC flags (>= 0.95): {'days_since_last_downgrade': 1.0}
LEAKAGE CHECK PASSED
```

Ablation: all three feature arms (STRUCTURED only; + RULE-VERIFIED; +
EVENT-CANDIDATE unverified) produce identical pooled PR-AUC/BSS to 4
decimal places -- the unverified EVENT-CANDIDATE arm adds nothing
measurable on this dataset.

**Bottom line, stated plainly**: this model has not been shown to beat
its own base rate with statistical confidence, on real data, at the
real sample size available (5 distinct positive events). This is the
honest headline result of the whole modelling effort to date, and is
carried forward unchanged from Phase 3 -- not softened here.

## Summary table

| Section | Tier | Headline |
|---|---|---|
| Classification | GOLD (test n=14) + silver context | rules macro-F1 0.635 [0.432, 1.000] |
| Extraction | SILVER-UNREVIEWED, PENDING_HUMAN_REVIEW | 6/6 real audit_firm fields validated, reproducible |
| Entity resolution | SILVER-UNREVIEWED, PENDING_HUMAN_REVIEW | 3/3 mentions correctly resolved; pairwise P/R/F1 not run (too thin) |
| Retrieval | SILVER-UNREVIEWED, PENDING_HUMAN_REVIEW | lexical_bm25 recall@10 0.667, MRR 0.330 (best of 3 methods) |
| Citation/verifier | SILVER-UNREVIEWED (agent-eval) / adversarial-GOLD | 0 unsupported-claim leakage across 740 claims; 14/14 adversarial PASSED |
| Risk model | SILVER-UNREVIEWED, INCONCLUSIVE | LightGBM PR-AUC 0.267 [0.099, 0.649] -- does not beat base rate with confidence |
