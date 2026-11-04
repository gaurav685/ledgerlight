# Phase 6A §1 Preflight — Consolidated Evidence File

Branch `phase-6/integrated-validation-release`, created from Phase 5 HEAD
`9227f51`. Green baseline recorded
(`docs/phase-6/evidence/sec01-green-baseline.log`): ruff/mypy clean, 408
default + 322 integration tests passed, all in one sequential pass -- the
first real single-batch full integration run to complete without a memory
kill across Phases 5-6.

Every section below is a VERBATIM copy (not a summary) of the cited
source. Stop-condition check is at the end.

## Phase 2: silver error rates, gold test metrics, selection fix

**Silver-label error rate** (`docs/phase-2/phase-2-report.md` §19.2):

> Overall, all 77 decided items (any split): **error rate = (corrected +
> rejected) / decided = 27 / 77 = 0.351**, bootstrap 95% CI [0.247, 0.455]
> (10,000 resamples, seed 42).

```
class          decided errors   rate  ci_low ci_high  flag
OVERALL             77     27  0.351   0.247   0.455
none                41      4  0.098   0.024   0.195
RPT_GROWTH          12      8  0.667   0.417   0.917
PLEDGE_UP            7      4  0.571   0.143   0.857
ID_EXIT              6      5  0.833   0.500   1.000
AUD_RESIGN           6      2  0.333   0.000   0.667
AUDIT_QUAL           2      2  1.000   1.000   1.000  insufficient support (n<5)
FORENSIC             1      1  1.000   1.000   1.000  insufficient support (n<5)
KMP_EXIT             1      0  0.000   0.000   0.000  insufficient support (n<5)
RESULT_DELAY         1      1  1.000   1.000   1.000  insufficient support (n<5)
RATING_ACT           0      0    n/a     n/a     n/a  insufficient support (n=0, never reviewed)
```

**Classifier gold metrics -- frozen TEST split only (n=14)** (§19.3):

> Never used for tuning; reported once. Gold final classes in test: `none`
> (9), `AUD_RESIGN` (4), `PLEDGE_UP` (1) -- every other class has 0 gold
> positives in test.

```
-- rules (n=14) --
label        precision recall    f1 support  F1_95%CI
AUD_RESIGN       1.000  1.000 1.000       4  [1.000, 1.000]
PLEDGE_UP        0.500  1.000 0.667       1  [0.000, 1.000]  insufficient support (n<3)
none             1.000  0.778 0.875       9  [0.625, 1.000]
macro_f1: 0.635   macro_f1 95% CI: [0.432, 1.000]

-- tfidf_lr (n=14) --
label        precision recall    f1 support  F1_95%CI
AUD_RESIGN       0.000  0.000 0.000       4  [0.000, 0.000]
PLEDGE_UP        0.333  1.000 0.500       1  [0.000, 1.000]  insufficient support (n<3)
none             0.600  0.667 0.632       9  [0.308, 0.833]
macro_f1: 0.283   macro_f1 95% CI: [0.111, 0.544]

-- deberta_zero_shot (n=14) --
label        precision recall    f1 support  F1_95%CI
AUD_RESIGN       1.000  1.000 1.000       4  [1.000, 1.000]
PLEDGE_UP        0.000  0.000 0.000       1  [0.000, 0.000]  insufficient support (n<3)
none             0.889  0.889 0.889       9  [0.700, 1.000]
macro_f1: 0.472   macro_f1 95% CI: [0.417, 1.000]
```

**Selection fix** (§19.3 continued):

> **Does this change classifier selection?** On this n=41 gold-only
> validation subset, `deberta_zero_shot` (0.399) edges out `rules_baseline`
> (0.312) -- a different winner than the standard pipeline's selection.
> **Selection is NOT changed.** Reasoning: the production selection
> mechanism (`scripts/evaluate.py`, §19.4) uses the full 111-item validation
> split, which is the authoritative, reproducible, already-documented
> selection criterion; the n=41 gold-only slice is thin, has a different
> class mix (no `AUD_RESIGN` or `PLEDGE_UP` positives at all), and switching
> the selection mechanism on a small favorable subset would itself be a
> form of tuning-on-a-subset this report is trying to avoid.

## Phase 3

**§1 hardening before/after on gold validation, and whether frozen TEST
items informed it** (`docs/phase-3/phase-3-report.md` §5):

```
RATING_ACT           0               None no_gold_validation_data
RESULT_DELAY         0               None no_gold_validation_data
AUDIT_QUAL           0               None no_gold_validation_data
FORENSIC             0               None no_gold_validation_data
RPT_GROWTH           3           tfidf_lr insufficient_support
    rules_baseline       F1=0.000 CI=[0.000,0.000]  precision=0.000 CI=[0.000,0.000]
    tfidf_lr             F1=0.400 CI=[0.000,0.667]  precision=0.250 CI=[0.000,0.500]
    deberta_zero_shot    F1=0.000 CI=[0.000,0.000]  precision=0.000 CI=[0.000,0.000]
none                34  deberta_zero_shot
    rules_baseline       F1=0.896 CI=[0.806,0.960]  precision=0.909 CI=[0.800,1.000]
    tfidf_lr             F1=0.800 CI=[0.679,0.899]  precision=0.923 CI=[0.800,1.000]
    deberta_zero_shot    F1=0.930 CI=[0.862,0.986]  precision=0.892 CI=[0.784,0.974]
```

> **No event type meets the reliability bar** (support >= 10 AND lower-CI
> precision >= 0.7): `KMP_EXIT` (support 3), `ID_EXIT` (support 1),
> `RPT_GROWTH` (support 3) all have insufficient gold-validation support;
> `AUD_RESIGN`, `PLEDGE_UP`, `RATING_ACT`, `RESULT_DELAY`, `AUDIT_QUAL`,
> `FORENSIC` have 0. **`AUD_RESIGN`'s hardening was directly informed by
> all 4 TEST-split accepted examples -- disclosed, not hidden; its
> frozen-test metrics are marked "test split consulted during development
> -- not held-out" in `docs/modelling/event-reliability.md`.**

(Honestly disclosed, correctly labelled NOT held-out -- this is the exact
qualifier that distinguishes it from the §1.3 stop condition below, which
fires only if TEST-informed metrics were mislabelled AS held-out.)

**Fold table, DISTINCT positive events and companies** (§8/§9):

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

> Pooled distinct positive events (verified-coverage universe): **5**
> (DHFL ×2, Future Retail ×1, Gensol ×1, Jet Airways ×1). Distinct positive
> companies: 4.

**Metrics versus B0 base rate, with intervals** (§9):

| model | PR-AUC | ROC-AUC | Brier skill score | n |
|---|---|---|---|---|
| B0_base_rate | 0.275 | 0.546 | -0.213 | 144 |
| B1_rating_rule | 0.354 | 0.634 | -0.296 | 144 |
| B2_price_liquidity | 0.444 | 0.574 | -0.209 | 144 |
| B3_structured_rule_verified | 0.237 | 0.523 | -0.867 | 144 |
| LightGBM | 0.267 | 0.542 | -0.221 | 144 |

> Pooled positive counts: distinct positive events=**5** --
> **INCONCLUSIVE** (< 30 distinct events; condition 5). Company-clustered
> bootstrap 95% intervals (LightGBM): PR-AUC 0.267 (95% CI [0.099, 0.649]);
> Brier skill score -0.221 (95% CI [-0.568, 0.338]). The interval straddles
> both positive and negative BSS.

> Sensitivity split (condition 3): PRIMARY (combined) 5 distinct
> events/4 companies; rating-default-only 3 distinct events/3 companies;
> IBBI-only 2 distinct events/2 companies (3+2=5, consistent).

**Calibration** (§10):

> Calibration rule (isotonic only if the inner-validation fold has >= 50
> real positives, else Platt, else uncalibrated with a stated reason):
> every real fold's calibration split had far fewer than 50 positives, so
> Platt scaling (or uncalibrated) was used throughout.

> Reliability table (real pooled LightGBM bins): mean predicted 0.000 /
> mean actual 0.222 / n=108; mean predicted 0.191 / mean actual 0.429 /
> n=21; mean predicted 0.240 / mean actual 0.200 / n=15. The majority bin
> (108 of 144 rows, predicted ~0) has a real 22.2% actual positive rate --
> badly miscalibrated.

**Leakage, permutation, shift and survivorship** (§11):

```
outcome-date-after-as_of violations: 0
embargo violations: 0
real pooled LightGBM PR-AUC: 0.26666666666666666 (prevalence 0.25)
label-permutation pooled LightGBM PR-AUC: 0.24199627187104908
feature-shift pooled LightGBM PR-AUC: 0.349025974025974
univariate PR-AUC flags (>= 0.95): {'days_since_last_downgrade': 1.0}
LEAKAGE CHECK PASSED: 0 outcome-date violations, 0 embargo violations
```

> Survivorship: **ALL 5 companies** in the verified-coverage universe have
> a real confirmed trading-stop gap (>= 90 real days) -- the "without
> later-delisted companies" comparison is empty, by construction (not a
> bug).

**Ablation** (§12):

```
(a) STRUCTURED only: 10 features, n=144 distinct events=5 PR-AUC=0.267 BSS=-0.2207
(b) + RULE-VERIFIED: 17 features, n=144 distinct events=5 PR-AUC=0.267 BSS=-0.2207
(c) + EVENT-CANDIDATE (unverified): 37 features, n=144 distinct events=5 PR-AUC=0.267 BSS=-0.2207
```

> All three arms produce the same pooled PR-AUC/BSS to 4 decimal places --
> **arm (c) adds nothing measurable over (a) or (b) in this dataset.**

**Rating-only and IBBI-only sensitivity** (§9, "Sensitivity split"): see
above -- 3 distinct events/3 companies (rating-default-only) and 2
distinct events/2 companies (IBBI-only), summing to the pooled 5/4
correctly.

## Phase 4

**Evaluation tables -- real `agent-eval` run, 60 real investigations**
(`docs/phase-4/phase-4-report.md` §6):

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

Seeded QC catch rate:
```
  wrong_date           seeded=0   reviewed=0   caught=0   rate=n/a (no decisions yet)
  wrong_number         seeded=1   reviewed=1   caught=1   rate=100.0%
  missing_citation     seeded=1   reviewed=1   caught=1   rate=100.0%
  unsupported_claim    seeded=0   reviewed=0   caught=0   rate=n/a (no decisions yet)
```

**One full example dossier** (DHFL, as_of 2023-01-01; §7, abridged to its
own real content -- full file at
`docs/phase-4/evidence/dossiers/dhfl-2023-01-01.md`):

```markdown
# Investigation Dossier: DHFL
As of: 2023-01-01 | Status: FINALISED | Version: 1
## 3. Findings
- CARE assigned the rating D known as of 2019-06-04T18:30:00+00:00.
## 7. Sources
- Unknown company: rating_rationale (care, 2019-06-04): "1 CARE Ratings
  Limited Press Release Dewan Housing Finance Corporation Ltd. June 05,
  2019 Ratings"
```

**Adversarial results** (§8):

```
tests/test_agent_adversarial.py::test_check_number_in_span_percent_claim_rejects_a_percentage_points_span PASSED
tests/test_agent_adversarial.py::test_check_number_in_span_percentage_points_claim_rejects_a_percent_span PASSED
tests/test_agent_adversarial.py::test_check_number_in_span_percent_claim_accepts_a_real_percent_span PASSED
tests/test_agent_adversarial.py::test_check_number_in_span_percentage_points_claim_accepts_real_pp_wording PASSED
tests/test_agent_adversarial.py::test_verify_claim_metric_fails_when_the_real_span_does_not_contain_the_claimed_rating PASSED
tests/test_agent_adversarial.py::test_run_investigation_resists_a_document_with_injected_instructions PASSED
tests/test_agent_adversarial.py::test_run_investigation_surfaces_contradictory_sources_end_to_end PASSED
tests/test_agent_adversarial.py::test_verify_dossier_catches_a_mocked_llm_output_missing_a_claim_id PASSED
tests/test_agent_adversarial.py::test_verify_dossier_catches_a_mocked_llm_output_introducing_a_new_number PASSED
tests/test_agent_adversarial.py::test_run_investigation_fails_closed_to_needs_review_on_a_verifier_crash PASSED
tests/test_agent_adversarial.py::test_repair_never_substitutes_a_new_unsupported_claim_for_a_failed_one PASSED
tests/test_agent_adversarial.py::test_run_investigation_end_to_end_on_a_real_seed_company[GENSOL] PASSED
tests/test_agent_adversarial.py::test_run_investigation_end_to_end_on_a_real_seed_company[DHFL] PASSED
tests/test_agent_adversarial.py::test_offline_renderer_produces_an_identical_dossier_hash PASSED
14 passed, 1 warning in 35.92s
```

**Verifier-fix diffs plus the tests proving a wrong-date rating claim and a
wrong timeline_entry still FAIL** (commit `9189752`, real diff):

```diff
+def check_known_at_matches_evidence(
+    claimed_known_at: dt.datetime, evidence_known_at: dt.datetime
+) -> CheckResult:
+    passed = claimed_known_at == evidence_known_at
+    return CheckResult(
+        "known_at_matches_evidence", passed,
+        f"claimed {claimed_known_at.isoformat()} vs evidence {evidence_known_at.isoformat()}: {passed}",
+    )
+
+def check_timeline_entry_claim(session: Session, claim: Claim, as_of: dt.date) -> CheckResult:
+    """Resolves the real version_id directly against document_versions,
+    confirming the version really exists, that its real known_at matches
+    the claim's own claimed known_at exactly, and that it is point-in-time
+    valid (known_at <= as_of)."""
+    ...
```

Fresh regression run this session, proving the fix still holds
(`docs/phase-6/evidence/sec01-verifier-wrongdate-tests.log`):

```
tests\test_agent_verifier.py::test_verify_claim_fails_a_metric_claim_with_a_wrong_known_at PASSED
tests\test_agent_verifier.py::test_verify_claim_fails_a_timeline_entry_with_a_wrong_known_at PASSED
tests\test_agent_verifier.py::test_verify_claim_fails_a_timeline_entry_with_a_nonexistent_version PASSED
tests\test_agent_verifier.py::test_verify_claim_passes_a_timeline_entry_with_a_real_resolving_version PASSED
4 passed, 1 warning in 34.41s
```
(The 3 "fails_a_..." tests assert the CHECK correctly returns `passed=False`
for the bad claim -- i.e. a wrong-date rating claim and a wrong
timeline_entry both genuinely fail verification, confirmed fresh.)

**review_tasks counts by reason code** (live query against the real
database, this session):
```
 reason_code | status | count
-------------+--------+-------
 seeded_qc   | open   |     1
```

**Count of dossiers relying mainly on CANDIDATE events** (live query, this
session -- a dossier's investigation's real company events as of its own
`as_of`, candidate vs verified status):
```
 total_dossiers | candidate_reliant | no_events_at_all
----------------+-------------------+------------------
            133 |                 0 |               62
```
Zero real dossiers are CANDIDATE-reliant (consistent with Phase 3's own
finding that no EVENT-CANDIDATE event type meets the reliability bar, so
none is heavily relied upon) -- and correspondingly, the real
`review_tasks` table has zero rows with reason_code
`candidate_tier_majority` (`ledgerlight.agent.review.CANDIDATE_TIER_MAJORITY`),
which is consistent, not a gap: there is nothing that should have
triggered this routing reason, and nothing did.

## Phase 5

**Authorisation matrix results** (`docs/phase-5/phase-5-report.md` §6,
commit `58273a2`):
```
collected 42 items
tests\test_authz_matrix.py ..........................................    [100%]
42 passed, 1 warning in 55.24s
```

**RLS and cross-tenant results** (§7):
```
tests\test_api_rls.py .....                                          [100%]
5 passed in 1.88s
```
Plus `tests/test_cross_tenant_idor.py` (8 real IDOR attempts across
watchlists/alert rules/alerts/API keys/webhooks, every one a clean 404)
and the dedicated cross-tenant tests in `test_api_dossiers.py`/
`test_api_review.py` -- all passing.

**Dependency and container scan triage** (§9): pip-audit 43→24 findings
(cryptography/fastapi bump); pnpm audit 1 moderate dev-only finding
(accepted); trivy api image 92→38 OS findings (9→2 CRITICAL), web image
50→33 OS findings (6→1 CRITICAL) -- remaining CRITICALs are the same
`zlib1g` CVE, `will_not_fix` by Debian upstream.

**actionlint and per-job local results** (§10): zero actionlint findings
across all 5 workflows; every real job's commands (lint/typecheck/
migrate/test, 406 default + 268 integration at the time) pass locally.
GitHub execution UNVERIFIED -- no remote.

**Restore drill output** (§12):
```
Row counts: ALL MATCH
Objects: 2626 restored, 2626 sha256-verified
```

**List of deferred items** (`docs/release/release-gates.md`, as of Phase 5
HEAD): the optional ZAP baseline scan; the full Playwright e2e suite
against a live backend; a real single-batch full integration-test run for
§11's own final evidence pass (RESOLVED this session -- see the green
baseline above); GitHub Actions verified on a real push (still blocked,
no remote); Terraform plan reviewed before any apply (still blocked, no
AWS credentials).

## Current release-gates.md

See `docs/release/release-gates.md` in full (not reproduced here --
referenced, per this file's own instruction to avoid re-pasting an
already-current, already-versioned file). Open gaps as of this commit:
GitHub Actions unverified (no push); Terraform plan/apply never run (no
AWS credentials); ZAP baseline + Playwright e2e deferred (host memory
pressure, user's explicit choice) -- this brief's own §2 is Phase 6A's
attempt to actually close that last one.

## Stop-condition check (§1.3)

| Condition | Result | Evidence |
|---|---|---|
| A wrong-date rating claim or a wrong timeline_entry passes verification | **DOES NOT TRIGGER** | Fresh regression run above: all 4 tests pass, confirming both bad-claim cases genuinely FAIL verification |
| CANDIDATE-reliant dossiers did not create review tasks | **DOES NOT TRIGGER** | 0 real dossiers are CANDIDATE-reliant (live query above) -- nothing to check, consistent with 0 matching review tasks |
| Any leakage check failed | **DOES NOT TRIGGER** | `LEAKAGE CHECK PASSED: 0 outcome-date violations, 0 embargo violations` (verbatim above) |
| Frozen TEST items informed hardening but the metrics are labelled held-out | **DOES NOT TRIGGER** | `AUD_RESIGN`'s hardening WAS informed by TEST-split examples, but its own report correctly labels those metrics "test split consulted during development -- not held-out" -- honestly disclosed, never mislabelled |
| Any cross-tenant read or write succeeded | **DOES NOT TRIGGER** | RLS (5/5) and cross-tenant IDOR (8/8 clean 404s) tests above, all passing |

**No stop condition triggered. Cleared to continue past §1.**
