# ADR 0006: Risk Modelling Approach (Phase 3)

## Status
Partially accepted (Phase 3, in progress). §1-5 decisions below are accepted and
implemented. §6-7 decisions are the planned design, not yet executed -- blocked on the
full-universe IBBI discovery crawl finishing (see `docs/phase-3/progress.md`).

## Context
Phase 3 builds point-in-time features, outcome labels, and (once unblocked) a
LightGBM risk model with walk-forward evaluation, over the real companies and documents
Phases 0-2 acquired and resolved. Every decision here is constrained by what the real
corpus actually contains, not by what a generic risk-modelling project would assume --
several decisions below exist specifically because a real check ruled out the simpler
assumption.

## Decisions

### Outcome definitions frozen before any feature or training code (§3)
`docs/modelling/outcomes.md` + `data/modelling/outcomes-v1.0.json` (sha256
`d879a2874d063b0025820ce52223e443b5b14d7c8746aa8d9e3117e4f3503e1b`), per the brief's own
explicit ordering requirement. Primary outcome: `IBBI_CIRP_ADMISSION` OR
`RATING_DOWNGRADE_D` within 12 months. This hash is stored in `model_registry` for every
experiment and must never change without a new, explicitly-versioned spec.

### Three real feature tiers, not one undifferentiated feature table (§4)
`feature_snapshots.feature_set_version` partitions by tier: `price-liquidity-1.0`
(STRUCTURED, UNIVERSE track, 228,678 real rows), `rule-verified-1.0` (RULE_VERIFIED,
UNIVERSE track, 3,241 real rows), `seed-governance-1.0` (EVENT_CANDIDATE, SEED track,
1,406 real rows). This directly implements the brief's feature policy: the PRIMARY model
uses STRUCTURED and RULE-VERIFIED only; EVENT-CANDIDATE enters only the ablation arm,
labelled unverified. Keeping them as separate `feature_set_version` rows (rather than one
wide table) makes that policy enforceable by a simple `WHERE` clause, not by convention.

### Financial features and GUIDANCE_MISS excluded, not attempted with unverified machinery
Both were assessed with real evidence before any extraction code was written (§4.3, §5):
financial-statement extraction measured ~40-50% real accuracy against a 7-sample manual
check (n=2 documents, nowhere near the brief's 90% span-verification bar); guidance
extraction found 0 real management-issued forward statements in 4,759 real pages
scanned. Building either anyway would mean shipping code with no real case to validate
it against. Both are tracked as open gaps in `docs/release/release-gates.md`, not
silently closed or faked with synthetic data.

### Known temporal-signal limitation in EVENT-CANDIDATE (SEED-track governance) features
A real, structural finding while building §4.3: documents from a non-"reliable" source
(a company's own investor-relations site) get `known_at = retrieved_at`, not their real
publish date (`ledgerlight.db.temporal`'s deliberate, conservative policy). Since every
such document in this corpus was fetched in one narrow window, trailing-window counts
built from them are a one-time step function, not a genuine time series. This is why
these features stay EVENT-CANDIDATE/ablation-only rather than being promoted -- the
limitation is structural to the data, not just the detector's own reliability tier.

### LightGBM, planned calibration, planned walk-forward protocol (§6-7, not yet executed)
Per the brief: LightGBM for the PRIMARY model; walk-forward evaluation with expanding
yearly outer folds and a >=12-month embargo (full protocol:
`docs/modelling/evaluation-protocol.md`). **A real, disclosed expectation stated in
advance**: the current pooled `PRIMARY_DISTRESS` positive count (34, pre-dedup, before
the IBBI crawl finishes) is close to or below the brief's own 30-positive floor for
"statistically inconclusive, no predictive-skill claim." This is named here, before any
model is trained, specifically so a later inconclusive result cannot be read as a
post-hoc excuse -- it is a realistic, disclosed possibility for this specific real
dataset's size.

### Training blocked on the full-universe IBBI crawl, by explicit user instruction
No §6/§7 work (train, tune, backtest) runs until the crawl finishes or is honestly
stopped with its real coverage recorded in `docs/modelling/data-quality.md`. The outcome
*definitions* stay frozen (unchanged spec hash); only the populated outcome *rows* refresh
once the crawl's new documents are extracted and `scripts/populate_outcomes.py` re-run.
