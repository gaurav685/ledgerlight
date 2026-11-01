# Phase 5 §1 Preflight — Verbatim Evidence and Audits

Branch `phase-5/api-ui-security` created from Phase 4 HEAD `d1daf12`. Green
baseline recorded (`preflight-01..04-*.log`): lint/format/typecheck clean,
380 default + 176 integration tests passed (one real pre-existing test
fragility found and cleaned up — see "Baseline note" below).

## §1.2 — Verbatim from docs/phase-3/phase-3-report.md

### Fold table, distinct positive events/companies per fold and pooled

```
coverage window: 2017-08-17 2026-07-21
companies: ['DHFL', 'FRETAIL', 'GENSOL', 'JETAIRWAYS', 'SPICEJET']
  year train_cutoff test_start   test_end  train_n  train_co train_pos  test_n  test_co test_pos
  2017   2015-01-01 2017-01-01 2018-01-01        0         0         0      15        3        0
  2018   2016-01-01 2018-01-01 2019-01-01        0         0         0      32        3        9
  2019   2017-01-01 2019-01-01 2020-01-01        0         0         0      29        3       12
  2020   2018-01-01 2020-01-01 2021-01-01       15         3         0      32        3        3
  2021   2019-01-01 2021-01-01 2022-01-01       47         3         9      21        2        9
  2022   2020-01-01 2022-01-01 2023-01-01       76         4        21       6        1        0
  2023   2021-01-01 2023-01-01 2024-01-01      108         4        24       5        1        0
  2024   2022-01-01 2024-01-01 2025-01-01      129         4        33       4        1        3
```

Pooled distinct positive events (verified-coverage universe): **5**
(DHFL ×2, Future Retail ×1, Gensol ×1, Jet Airways ×1 — SpiceJet has 2
real raw events but 0 labeled positives, correctly censored by
`unknown_trading_stop`). Unrestricted-universe pooled distinct positive
companies: 31.

### Metrics tables (models vs. B0) with intervals

| model | PR-AUC | ROC-AUC | Brier skill score | n |
|---|---|---|---|---|
| B0_base_rate | 0.275 | 0.546 | -0.213 | 144 |
| B1_rating_rule | 0.354 | 0.634 | -0.296 | 144 |
| B2_price_liquidity | 0.444 | 0.574 | -0.209 | 144 |
| B3_structured_rule_verified | 0.237 | 0.523 | -0.867 | 144 |
| LightGBM | 0.267 | 0.542 | -0.221 | 144 |

Pooled positive counts: distinct positive events=**5** —
**INCONCLUSIVE** (< 30 distinct events). Company-clustered bootstrap
95% CI (LightGBM): PR-AUC 0.267 [0.099, 0.649]; Brier skill score
-0.221 [-0.568, 0.338] — the interval straddles both positive and
negative BSS.

### Calibration choice and reason

Platt scaling (or uncalibrated where the inner split lacked two real
classes) throughout — every real fold's calibration split had far
fewer than the 50-positive isotonic threshold.

### Leakage, permutation, feature-shift, survivorship

```
outcome-date-after-as_of violations: 0
embargo violations: 0
real pooled LightGBM PR-AUC: 0.26666666666666666 (prevalence 0.25)
label-permutation pooled LightGBM PR-AUC: 0.24199627187104908
feature-shift pooled LightGBM PR-AUC: 0.349025974025974
univariate PR-AUC flags (>= 0.95): {'days_since_last_downgrade': 1.0}
LEAKAGE CHECK PASSED: 0 outcome-date violations, 0 embargo violations
```

Disclosed anomaly: feature-shift PR-AUC (0.349) is higher than
unshifted (0.267) — attributed to long same-episode label runs in this
sparse dataset, not a demonstrated leak. The deliberately-leaky
synthetic feature required by Phase 3's own §7 **IS caught**
(`tests/test_leakage.py`, PR-AUC exactly 1.0). Survivorship: all 5
companies in the verified-coverage universe have a confirmed
trading-stop gap; "without later-delisted companies" is empty by
construction, not a bug.

### Ablation

```
(a) STRUCTURED only: 10 features, n=144 distinct events=5 PR-AUC=0.267 BSS=-0.2207
(b) + RULE-VERIFIED: 17 features, n=144 distinct events=5 PR-AUC=0.267 BSS=-0.2207
(c) + EVENT-CANDIDATE (unverified): 37 features, n=144 distinct events=5 PR-AUC=0.267 BSS=-0.2207
```

All three arms produce the same pooled PR-AUC/BSS to 4 decimal places.

### Rating-only and IBBI-only sensitivity results

Sensitivity split (`ledgerlight.modelling.sensitivity`): PRIMARY
(combined) 5 distinct events/4 companies; **rating-default-only 3
distinct events/3 companies**; **IBBI-only 2 distinct events/2
companies** (3+2=5, consistent).

### Whether frozen TEST items informed §1 detector hardening, and the resulting held-out status

**Yes, for `AUD_RESIGN` only, disclosed, not hidden.** From the report
(§5 and §16): "`AUD_RESIGN`'s hardening was directly informed by all 4
TEST-split accepted examples — disclosed, not hidden; its frozen-test
metrics are marked 'test split consulted during development — not
held-out' in `docs/modelling/event-reliability.md`." §16's own
limitations list repeats this verbatim: "`AUD_RESIGN`'s frozen-test
metrics are not a clean held-out result (test-split consultation
during §1.4 hardening, disclosed in full in
`docs/modelling/event-reliability.md`)." **The metrics are correctly
labelled "not held-out," never mislabeled as held-out** — confirmed by
re-reading `docs/modelling/event-reliability.md` directly: "`AUD_RESIGN`'s
frozen-test metrics below are marked 'test split consulted during
development — not held-out.' They are still printed, since hiding
them would be worse than disclosing them, but they must not be read as
an unbiased held-out result."

### Phase 3's own exit-gate checklist (§19)

| # | Gate | Status |
|---|---|---|
| 1 | Test split/gold labels frozen; detectors hardened; reliability tiers documented | PASS |
| 2 | Universe data expanded within compliance; entity-link rates reported | PASS (partial coverage, disclosed) |
| 3 | Outcomes frozen and hashed; censoring handled; evidence spans | PASS (human review pending) |
| 4 | 100% of feature rows point-in-time clean; later-delisted companies included | PASS |
| 5 | Guidance extraction limits stated | PASS (limits stated) |
| 6 | B0-B3 and LightGBM evaluated walk-forward | PASS |
| 7 | Calibration justified; SHAP stored | PASS |
| 8 | All leakage checks pass, including the deliberately-leaky feature | PASS (2 anomalies disclosed) |
| 9 | Ablation reported, including null results | PASS |
| 10 | Model card/experiment reports complete; inconclusive labelled | PASS |
| 11 | Backtest reproducibility proven; secret scan clean | PASS |
| 12 | Committed locally, no AI attribution, bundle verified, nothing pushed | PASS |

No gate is FAIL.

## §1.3 — Verbatim from docs/phase-4/phase-4-report.md

### One full example dossier (Markdown)

See `docs/phase-4/phase-4-report.md` §7 in full (DHFL, as_of
2023-01-01, FINALISED) — not re-pasted here to avoid duplicating a
large block; identical content, unchanged.

### Evaluation tables

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

### Adversarial test list with results

```
test_check_number_in_span_percent_claim_rejects_a_percentage_points_span PASSED
test_check_number_in_span_percentage_points_claim_rejects_a_percent_span PASSED
test_check_number_in_span_percent_claim_accepts_a_real_percent_span PASSED
test_check_number_in_span_percentage_points_claim_accepts_real_pp_wording PASSED
test_verify_claim_metric_fails_when_the_real_span_does_not_contain_the_claimed_rating PASSED
test_run_investigation_resists_a_document_with_injected_instructions PASSED
test_run_investigation_surfaces_contradictory_sources_end_to_end PASSED
test_verify_dossier_catches_a_mocked_llm_output_missing_a_claim_id PASSED
test_verify_dossier_catches_a_mocked_llm_output_introducing_a_new_number PASSED
test_run_investigation_fails_closed_to_needs_review_on_a_verifier_crash PASSED
test_repair_never_substitutes_a_new_unsupported_claim_for_a_failed_one PASSED
test_run_investigation_end_to_end_on_a_real_seed_company[GENSOL] PASSED
test_run_investigation_end_to_end_on_a_real_seed_company[DHFL] PASSED
test_offline_renderer_produces_an_identical_dossier_hash PASSED
14 passed, 1 warning in 35.92s
```

## §1.4 — Verifier-fix audit

### Bug 1 + 2 (found by Phase 4's real agent-eval run, fixed in commit `379fa27`)

Full diff:
```diff
-EVIDENCE_EXEMPT_CLAIM_TYPES = frozenset({"risk_signal", "limitation"})
+EVIDENCE_EXEMPT_CLAIM_TYPES = frozenset({"risk_signal", "limitation", "timeline_entry"})
+"""`timeline_entry` belongs here alongside `risk_signal`/`limitation`:
+...fixed here rather than in the claims.py docstring."""

-        known_at_str = claim.payload.get("known_at")
-        if isinstance(known_at_str, str):
-            try:
-                claimed_date = dt.datetime.fromisoformat(known_at_str).date()
-                checks.append(check_date_in_span(resolved.data.text, claimed_date))
-            except ValueError:
-                pass
+        # Scoped to event claims only: ...
+        if claim.claim_type == "event":
+            known_at_str = claim.payload.get("known_at")
+            if isinstance(known_at_str, str):
+                try:
+                    claimed_date = dt.datetime.fromisoformat(known_at_str).date()
+                    checks.append(check_date_in_span(resolved.data.text, claimed_date))
+                except ValueError:
+                    pass
```

**Justification 1** (`timeline_entry` exemption): `claims.py`'s own
docstring already documented this claim type as sharing the empty-
evidence exemption with `risk_signal`/`limitation` — a filing-exists
claim has no specific text span to cite. The constant simply never
matched that documented intent. Real impact: 237 real claims wrongly
removed in REPAIR before the fix.

**Justification 2** (`date_in_span` scoped to events): a care_rating
claim's real evidence span is the rating symbol's own regex capture
group (`ledgerlight.modelling.rating_features.py`) — structurally
never a date-bearing sentence. Checking a date against it could never
pass. Real impact: 143 real claims wrongly removed in REPAIR before
the fix.

### Bug 3 + 4 (found by THIS preflight, fixed in commit `9189752`)

Checking whether bugs 1+2's fixes left a blind spot — per this
brief's own explicit request — found two real gaps the fixes
themselves introduced:

- Scoping `date_in_span` away from metric claims removed the ONLY
  check that compared a care_rating claim's `known_at` to anything —
  `point_in_time` only checks the EVIDENCE's `known_at` against
  `as_of`, never against the claim's own `known_at`. **A wrong-dated
  rating claim would have passed uncaught.** Fixed with
  `check_known_at_matches_evidence`.
- Making `timeline_entry` blanket-exempt (identical treatment to
  `risk_signal`/`limitation`) meant no wrong date or reference could
  ever fail it, even though — unlike those two — a `timeline_entry`
  claim DOES carry a real, checkable fact (its `document_version_id`).
  **A wrong-dated or fabricated timeline_entry would have passed
  uncaught.** Fixed with `check_timeline_entry_claim`.

### Regression tests proving a WRONG-date rating claim still FAILS (through the check that now covers rating dates)

```
tests/test_agent_verifier.py::test_verify_claim_fails_a_metric_claim_with_a_wrong_known_at PASSED
```
Real assertion: a care_rating claim with `known_at="2019-06-15..."`
against a real evidence document whose own real `known_at` is
`2020-01-01` — correct rating symbol, correct span text, WRONG claimed
date — fails overall, specifically via `known_at_matches_evidence`
(`passed=False`).

### Proof that a WRONG timeline_entry (date or value) still FAILS

```
tests/test_agent_verifier.py::test_verify_claim_fails_a_timeline_entry_with_a_wrong_known_at PASSED
tests/test_agent_verifier.py::test_verify_claim_fails_a_timeline_entry_with_a_nonexistent_version PASSED
tests/test_agent_verifier.py::test_verify_claim_passes_a_timeline_entry_with_a_real_resolving_version PASSED
```
Real assertions: a `timeline_entry` claiming a `known_at` that
mismatches its own real `document_version`'s `known_at` fails; a
`timeline_entry` referencing a `version_id` that does not exist in
`document_versions` fails; the correct, matching case still passes.

Full suite re-run after this fix: 380 default + 179 integration
passed (`docs/phase-5/evidence/preflight-0{3,4}-test*.log` — the `04`
log reflects the state AFTER this fix, run a second time; see the
"Baseline note" below for why a first run differed).

## §1.5 — Review routing audit

Scoped to the real, final (post-Phase-4-fix) 60-investigation
`agent-eval` run (the most recent 60 investigations with
`requested_by='agent-eval'`):

```sql
SELECT rt.reason_code, count(*) FROM review_tasks rt
JOIN dossiers d ON d.id = rt.dossier_id
WHERE d.investigation_id = ANY(<those 60 ids>)
GROUP BY rt.reason_code;
```
Result: **empty — 0 review tasks of any reason code.**

Dossiers relying mainly on CANDIDATE events (independently verified
directly against real claim tiers, not just via routing, so the
absence of a routing task cannot hide a real miss):
```sql
SELECT i.id,
       count(*) FILTER (WHERE c.payload->>'tier' = 'CANDIDATE') AS candidate_n,
       count(*) AS event_n
FROM investigations i JOIN claims c ON c.investigation_id = i.id AND c.claim_type = 'event'
WHERE i.id = ANY(<those 60 ids>) GROUP BY i.id;
```
16 of 60 investigations have ≥1 real event claim; **0 of those 16 have
`candidate_n > event_n/2`** (every one is majority or fully VERIFIED
tier). **0 dossiers relying mainly on CANDIDATE events, and
therefore 0 missed review tasks for that reason** — the stop
condition ("dossiers relying mainly on CANDIDATE events did not
produce review tasks") is vacuously satisfied, not silently failing.

## Baseline note (not a Phase 5 code defect)

The first integration-suite run this session (before the bug-3/4 fix
above) failed one test —
`test_agent_qc_seed.py::test_compute_catch_rate_report_counts_a_wrong_approve_as_not_caught`
— because two real, legitimate seeded-QC rows from Phase 4's own §11
evidence capture (decided `reject`, correctly) were still sitting in
the local dev DB, and `compute_catch_rate_report` queries globally,
not scoped to one test run. Cleaned up (deleted those two specific
investigation-scoped rows; their evidence already lives in the
committed `docs/phase-4/evidence/sec11-08..10-*.log` files, so nothing
is lost). A real, disclosed design fragility
(`docs/evaluation/phase-4-agent-evaluation.md`'s own note on this
function's global scope) — not fixed here, since doing so would mean
reopening Phase 4's own closed work beyond what Phase 5's baseline
actually needs.
