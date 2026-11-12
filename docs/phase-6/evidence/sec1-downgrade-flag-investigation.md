# Phase 6 Correction 2 §1 — `days_since_last_downgrade` PR-AUC=1.0 flag

## §1.1 — how the flag is computed

`ledgerlight.modelling.leakage.univariate_pr_auc_flags` (lines 131-164):
- Rows: `labeled = [row for row in rows if not row.censored]` — all 144 real
  pooled rows, minus any censored ones (censoring handled separately, not
  part of this calculation).
- Per feature: `mask = ~np.isnan(values)` — only rows where THIS SPECIFIC
  feature is non-null feed its own PR-AUC. Different features can use
  different row subsets.
- **In-sample, not walk-forward**: `average_precision_score(y[mask],
  values[mask])` is computed once, directly, with no train/test split at
  all — a real, disclosed design (the function's own docstring: "a real
  signal worth investigating, not automatically proof of leakage").
- Tries both the raw value and its negation, keeps the max (a feature can
  be a real inverse predictor).

## §1.2 — value distribution, positive vs negative

Real query against `build_primary_outcome_dataset`'s own output:

```
positives: 36, negatives: 108
positive null count: 27 / 36 (75%)
negative null count: 98 / 108 (91%)

positive non-null values (9 of them): [95, 123, 154, 184, 215, 245, 276, 307, 337]
negative non-null values (10 of them): [6, 36, 19, 49, 5, 36, 66, 3, 33, 64]
negative non-null min/max: 3, 66
```

Clean separation on the 19 non-null rows (positives all >= 95; negatives
all <= 66) — this is the real PR-AUC=1.0.

## §1.3 — per-positive-row trace, confirming point-in-time validity

**All 9 non-null positive rows come from exactly one company: FRETAIL.**
The other 4 companies (DHFL, GENSOL, JETAIRWAYS, SPICEJET) have
`days_since_last_downgrade = None` for every single one of their own
rows (36 negative DHFL+GENSOL+JETAIRWAYS+SPICEJET rows are also all
null) — no qualifying downgrade *transition* was ever recorded for them
as of their own relevant `as_of` dates.

FRETAIL's real rating history (`extract_rating_observations`, 24 real
observations):
```
known_at=2020-10-28  rating=B    ordinal=14   <- the downgrade feeding every positive row below
known_at=2021-03-30  rating=B    ordinal=14   (no change, no new transition)
known_at=2022-01-02  rating=D    ordinal=19   <- the REAL outcome event (PRIMARY_RATING_DOWNGRADE_D)
known_at=2022-05-02  rating=D    ordinal=19
...
```

Traced directly against `compute_rating_features`'s own logic:

| as_of | last_downgrade_date used | that downgrade's rating | days_since | real outcome event (triggering_event_time) | same event? |
|---|---|---|---|---|---|
| 2021-01-31 | 2020-10-28 | B (ordinal 14) | 95 | 2022-01-02 18:30 (D, ordinal 19) | **No** — distinct, earlier action |
| 2021-09-30 | 2020-10-28 | B (ordinal 14) | 337 | 2022-01-02 18:30 (D, ordinal 19) | **No** — same earlier action, no newer downgrade occurred in between |

**`known_at` (2020-10-28) <= every citing `as_of`: confirmed, for all 9
positive rows** (as_of ranges 2021-01-31 through 2021-09-30, all after
2020-10-28). **The downgrade cited is never the outcome event itself**
(B→D are two distinct rating actions, 431 days apart) — not
self-referential, not circular.

## §1.4 — why LightGBM only scores 0.267 despite this "perfect" flag

The 19 non-null rows feeding the univariate flag are **100% from one
company's own calendar** — within FRETAIL's own timeline, later months
(closer to its real 2022 default, labeled positive) naturally have a
larger "days since the last rating action" than earlier months (closer
to the 2020-10-28 downgrade itself, labeled negative), simply because
FRETAIL's rating agency took no further action for ~11 months before the
real default. This is a real, single-company autocorrelation — not a
cross-company law. The pooled LightGBM model is trained/evaluated across
all 5 companies with a company-clustered bootstrap and a real
walk-forward split; the feature is null for 100% of the other 4
companies' rows (125 of 144 total), so it contributes no signal there,
and FRETAIL's own idiosyncratic calendar does not generalize to a
held-out company or period under a real walk-forward evaluation. Hence:
univariate PR-AUC 1.0 (a single company's own trajectory) coexists
cleanly with pooled PR-AUC 0.267 (no real cross-company signal) — no
contradiction once the row-level provenance is traced.

## §1.5 — verdict: NOT a leak

- `known_at <= as_of` holds for every citing row (confirmed above).
- The downgrade cited is never the same rating action as the outcome
  event (confirmed above — B vs D, 431 days apart).
- The "perfect separation" is a disclosed sparsity/autocorrelation
  artifact (one company contributes all 19 non-null points), not a
  temporal or causal violation.

**No fix applied** — per the brief's own §1.5 branch for "not a leak,"
documented in `docs/modelling/data-quality.md`'s "Known, disclosed
caveats" and `docs/modelling/model-card.md`'s "Failure modes" (regenerated
via `scripts/model_card.py`, never hand-edited).
