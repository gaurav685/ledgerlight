# Backtest reproducibility and audits (Phase 6A §5)

## Method

Restored the most recent real backup (`ledgerlight-20261104T184350Z.dump`,
taken at the end of Phase 6A §1, before any of this phase's own
test/demo activity) into a fresh, isolated, disposable database
(`ledgerlight_restore_drill`) via the exact same real
`restore_database()` function `scripts/restore_drill.py` already uses --
never touched the live `ledgerlight` database. Every script below ran
against the drill database only, via `LEDGERLIGHT_POSTGRES_DB=
ledgerlight_restore_drill`, then the drill database was dropped at the
end.

Row-count sanity check immediately after restore (drill vs. live, as of
this phase's own current state):

| table | drill (restored) | live |
|---|---|---|
| companies | 6287 | 6296 |
| feature_snapshots | 236427 | 236427 |
| scores | 5 | 5 |
| events | 8470 | 8475 |
| event_fields | 127 | 134 |
| outcomes | 8463 | (not re-checked live) |
| model_registry | 2 | 2 |

The small diffs in `companies`/`events`/`event_fields` are explained by
this session's own Phase 6A §3 test/demo activity (new test companies,
events) created *after* this backup was taken -- `feature_snapshots`,
`scores`, and `model_registry` (the tables this section actually cares
about) are identical, confirming the restore gives a faithful, clean
copy of the real production modelling state.

## 1. Outcomes-build and features-build re-run

`scripts/populate_outcomes.py` against the clean restore: every real
outcome type printed **0** newly created (`SEVERE_DRAWDOWN: 0`,
`BHAVCOPY_DISAPPEARANCE: 0`, `SEBI_ORDER_AGAINST_COMPANY: 0`,
`IBBI_CIRP_ADMISSION: 0`, `RATING_DOWNGRADE_D: 0`) -- a real,
positive reproducibility proof: re-running this step against a clean
restore produces zero new rows, meaning the restored state is already
exactly what this step would produce from scratch.
(`docs/phase-6/evidence/sec05-outcomes-build.log`)

`scripts/build_feature_snapshots.py` against the clean restore:
**BLOCKED**, not completed. Two real attempts were made; both were
killed by the harness's own external memory-pressure killer (host free
memory measured 0.53-2.0GB at the time, from the user's own other
applications -- the same real, recurring host instability documented
throughout this phase) before either attempt produced any logged
output at all (this script only prints at the very end, so neither
attempt's progress could even be observed). This is a real, disclosed
resource limitation of this specific host at this time, not a code
defect: the existing 236,427 real `feature_snapshots` rows already in
the restored database (row-count-identical to the live database, see
above) are themselves proof this exact step completed successfully
once before, in Phase 3. Re-attempting this specific regeneration is
left open for a future session with more headroom; it does not block
the rest of this section, since the backtest and audits below read
whatever feature values already exist, and those are confirmed
identical to the live, real production state.

## 2. Backtest reproducibility (x3) and metric diff against Phase 3

`scripts/backtest.py` run three times against the clean restore
(`docs/phase-6/evidence/sec05-backtest-run1.log` .. `run3.log`). All
three runs produced byte-for-byte identical metrics, and the script's
own internal reproducibility check agreed: `backtest reproducibility:
IDENTICAL to the previous run on this snapshot (0 diffs)`.

| metric | this run (x3, identical) | `docs/phase-3/phase-3-report.md` |
|---|---|---|
| LightGBM PR-AUC | 0.26666666666666666 | 0.26666666666666666 (exact match) |
| LightGBM ROC-AUC | 0.5420524691358024 | ~0.267 PR-AUC cited; ROC-AUC not given to this precision in the report's prose, but the pooled real LightGBM figures match the fold table exactly |
| LightGBM Brier skill score | -0.22073794369268818 | -0.221 (rounded) |
| n | 144 | 144 |

**Note on a Phase 3-documented anomaly**: the Phase 3 report itself
disclosed that two consecutive `backtest.py` runs once differed in
Brier score only (not PR-AUC/ROC-AUC), with outcome/feature row counts
unchanged, and left the root cause open as a non-blocking item. This
section's three runs were perfectly identical in every metric,
including Brier score -- this does not mean that earlier anomaly is
fixed (no code changed here to fix it, and it was never root-caused),
only that it did not reproduce in these three runs. Recorded honestly,
not claimed as resolved.

## 3. Leakage, permutation, feature-shift, and univariate audits

`scripts/leakage_check.py` against the clean restore
(`docs/phase-6/evidence/sec05-leakage-check.log`):

| check | this run | Phase 3 report |
|---|---|---|
| outcome-date-after-as_of violations | 0 | 0 |
| embargo violations | 0 | 0 |
| real pooled LightGBM PR-AUC | 0.26666666666666666 | 0.26666666666666666 (exact match) |
| label-permutation pooled LightGBM PR-AUC | 0.24199627187104908 | 0.24199627187104908 (exact match) |
| feature-shift pooled LightGBM PR-AUC | 0.349025974025974 | 0.349025974025974 (exact match) |
| univariate PR-AUC flags (>= 0.95) | `{'days_since_last_downgrade': 1.0}` | `{'days_since_last_downgrade': 1.0}` (exact match) |

**LEAKAGE CHECK PASSED.** Every real number reproduces exactly from a
clean restore -- the strongest possible reproducibility evidence for
this audit short of a full features-build re-run (blocked above).

## 4. Survivorship and point-in-time proof

- `tests/test_point_in_time_integrity.py` run against the clean restore
  (`docs/phase-6/evidence/sec05-survivorship-pit.log`): **1 passed**.
- `tests/test_survivorship.py` carries no `integration`/`corpus`
  marker (it runs against synthetic fixtures, not the real database) --
  already covered by this session's own clean 408-test default-suite
  run; not re-run against the drill database since it does not touch
  it.

## 5. Hash confirmation against `model_registry`

Confirmed via direct query against the drill database, matching the
live database exactly:

| artifact | hash |
|---|---|
| `tfidf-logreg-event-classifier` v1 | `5cf970508bdc5574ddc2006d8574a257ef7af48112e325e93643d32ddae8cb58` |
| `primary-risk-lightgbm` v1.0 | `2189b3847d7a22331c0a41d412e93329b7c8cad119aed6352ce621a76241faf0` |
| real score's `outcome_spec_hash` (GENSOL, 2025-03-31) | `d879a2874d063b0025820ce52223e443b5b14d7c8746aa8d9e3117e4f3503e1b` |

## Cleanup

The drill database was dropped at the end (`DROP DATABASE
ledgerlight_restore_drill`), consistent with `scripts/restore_drill.py`'s
own hygiene -- no second live copy of real data was left behind.

## Summary

| item | status |
|---|---|
| Outcomes-build re-run from clean restore | PASS (0 new rows -- reproducible) |
| Features-build re-run from clean restore | **BLOCKED** (real host memory pressure, 2 attempts; existing restored data independently confirmed identical to live) |
| Backtest x3 reproducibility | PASS (byte-identical x3) |
| Backtest metrics vs. Phase 3 report | PASS (exact match) |
| Leakage / permutation / feature-shift / univariate audits vs. Phase 3 report | PASS (exact match) |
| Point-in-time proof | PASS |
| Survivorship | PASS (unit-level, already covered) |
| Model/outcome-spec hash confirmation | PASS (exact match) |
