# LEDGERLIGHT — PHASE 3: TEMPORAL INTELLIGENCE AND QUANTITATIVE RISK MODELLING

You are implementing Phase 3 of Ledgerlight. Phase 2 is on branch phase-2/knowledge-extraction-entity-resolution (HEAD bc69c29) and provides:
- knowledge schema, taxonomy v1.0, classifiers, span-verified extraction, entity resolution, hybrid retrieval
- 242 tests
- Phase 1 ingestion: SEBI, IBBI, CARE, company IR sites, NSE bhavcopy (876k rows), Dagster, Garage

Human gold review of 80 event items (reviewer: Gaurav) found:
- silver-label error rate 35.1% [24.7–45.5%]
- worst types: ID_EXIT 83%, RPT_GROWTH 67%, PLEDGE_UP 57%, AUD_RESIGN 33%, mostly boilerplate over-firing
- no event type is yet reliable for modelling
- field, entity-pair and retrieval gold are DEFERRED_TO_PHASE_6

Read before changing anything:
- docs/phase-2/phase-2-report.md
- docs/evaluation/phase-2-evaluation.md
- docs/knowledge/*.md
- docs/data/temporal-semantics.md
- docs/data/feasibility-assessment.md
- docs/release/release-gates.md
- docs/adr/*

Scope:
- detector hardening (§1)
- point-in-time features and outcome definitions
- guidance extraction and matching
- risk modelling, calibration and interpretability
- walk-forward evaluation, leakage and survivorship controls
- the model card and experiment reports

Do NOT implement:
- the investigation agent (Phase 4)
- API endpoints or frontend (Phase 5)
- release work (Phase 6)
Stop at the Phase 3 boundary.

## 0. GROUND RULES

- All earlier ground rules apply:
  - honest UA, no bypass, respect robots.txt and terms (CRISIL exclusion), BLOCKED sources unschedulable
  - no fabrication, no sudo, no account creation
  - no secrets or raw data in git
- Never hardcode, round up or cherry-pick metrics. Report negative and inconclusive results plainly.
- Never review or relabel gold items yourself. Never tune on the frozen test split.
- Strict temporal integrity:
  - every feature value at as_of uses only data with known_at <= as_of
  - every outcome window starts strictly after as_of
- Neutral language. A risk score is an analytical signal, not a statement of wrongdoing, and not investment advice.
- GIT POLICY: commit locally only. No remote, no push.

## 1. PREFLIGHT: SELECTION FIX AND DETECTOR HARDENING

1. Branch phase-3/temporal-risk-modelling from bc69c29. Run the full checks and record a green baseline.
2. Freeze the evaluation data:
   - Write data/manifests/frozen-test-split-phase2.json (item IDs plus the sha256 of the sorted IDs).
   - Write data/manifests/gold-labels-phase2.json (gold item IDs, final labels, reviewer, sha256).
   - Add a guard test that fails if any training, tuning or threshold-selection code reads frozen test items.
3. FIX the circular model selection:
   - Classifier selection must use GOLD validation items only (currently n=41). Silver validation labels were produced by the keyword rule, which made rules_baseline score 1.000 circularly.
   - Re-select per event type on gold validation. Report it with bootstrap intervals and flag low support.
   - Document the change in ADR 0005.
4. Harden the detectors against boilerplate. Changes are informed ONLY by dev-split and gold-validation errors, never test.
   - Negative context suppression: policy statements, "disclosed in Note X", governance-report boilerplate, definitions, tables of contents.
   - Evidence requirements per type:
     - AUD_RESIGN: resignation language, plus statutory auditor reference, plus a date or effective date
     - KMP_EXIT / ID_EXIT: resignation or cessation language, plus a named person, plus a role
     - RPT_GROWTH: numeric related-party amounts for at least 2 periods
     - PLEDGE_UP: computed ONLY from structured shareholding or encumbrance numbers, never from free-text mentions
     - AUDIT_QUAL: an opinion heading (Qualified, Adverse or Disclaimer), with Emphasis of Matter handled per taxonomy v1.0
   - Bump the detector and classifier versions. Re-run the pipeline: new event versions with supersedes links, nothing overwritten.
   - Report, on gold validation before and after hardening: per-type precision, recall and support, with intervals, and the estimated stored-event false-positive counts. Then report test metrics ONCE, after all changes are final.
   - Commit this work with "phase-2:" prefixed messages.
5. Event reliability tiers, written to docs/modelling/event-reliability.md:
   - VERIFIED: the event itself is human-accepted gold
   - CANDIDATE: detector output, not reviewed
   Record per-type gold precision and intervals. No event type may be described as reliable unless its gold-validation precision has a lower 95% bound of at least 0.7 with support of at least 10. Report which types, if any, meet this.
6. Print the post-hardening knowledge statistics: events by type, status and tier, per source, with date ranges.

## 2. DATA EXPANSION FOR A MARKET-WIDE UNIVERSE (compliant sources only)

Use the existing Phase 1 jobs, same rate limits and robots rules, AVAILABLE sources only.

1. NSE bhavcopy:
   - Run the documented full-range backfill as far back as the archive legitimately provides, with a target of 2012 to present.
   - Handle the format changes and report date gaps.
   - If the run would exceed about 6 hours, run as much as possible, record progress, and document the resume command.
2. CARE rationales: broaden to all available rationales, and record coverage. Other agencies only if already marked AVAILABLE; ICRA and CRISIL stay excluded.
3. SEBI orders and IBBI public announcements: full available history.
4. Link names and CINs to companies (ISIN/symbol) via Phase 2 entity resolution.
   - Report per source: auto-linked, review-queued, unmatched.
   - Only AUTO-LINKED links may be used for outcomes or features. Report the exclusion counts.

## 3. OUTCOME DEFINITIONS (define and freeze BEFORE any training)

Write docs/modelling/outcomes.md and an outcomes spec file. Store the spec's sha256 in model_registry for every experiment.

- PRIMARY outcome — severe credit or insolvency distress within H = 12 months after as_of: any one of
  - an IBBI CIRP admission or public announcement for the company
  - a rating downgrade to default grade (D or equivalent) by an AVAILABLE agency
  Event date = the earliest trustworthy known_at.
  - Rating-default extraction must pass span verification: the rating symbol and date are present in the cited span.
  - IBBI linking must be auto-linked.
- SECONDARY outcomes, each reported separately:
  - (a) a severe relative drawdown: 12-month return at least X percentage points below the market median, with X defined and justified
  - (b) a SEBI final or interim order against the company or its promoters, via auto-linked entities
  - (c) disappearance from bhavcopy without an identifiable corporate action. Document that this is noisy, because mergers cannot be fully distinguished.
- Censoring for unknown trading stops and end-of-window observations is handled explicitly and documented. Never silently label these negative.
- Populate the outcomes table with: evidence (version, page, span), event dates, known_at, and the spec version.
- Write docs/modelling/outcome-evidence-review.csv listing EVERY positive primary-outcome event with its evidence span, for human spot-check in Phase 6. Add to docs/release/release-gates.md: "Human spot-check of primary-outcome evidence completed before release."

## 4. POINT-IN-TIME FEATURES

Migrations:
- feature_definitions: name, version, description, inputs, provenance tier, as_of semantics, lookback, track
- feature_snapshots: company_id, as_of, feature_set_version, values, max_input_known_at, data-quality flags

Snapshots are monthly (month-end as_of) from 2014 onwards where the data allows. The universe at each as_of is the companies trading in that period's bhavcopy, INCLUDING those later delisted.

Provenance tier for every feature:
- STRUCTURED: price, volume or turnover
- RULE-VERIFIED: rule-extracted and span-verified, e.g. rating symbols and actions, IBBI and SEBI history via auto-links
- EVENT-CANDIDATE: built from Phase 2/§1 detector events that are not human-verified

Feature policy (mandatory):
- The PRIMARY model uses STRUCTURED and RULE-VERIFIED features only.
- EVENT-CANDIDATE features enter ONLY in the ablation arm, labelled unverified.
- They can be promoted only for event types meeting the §1.5 reliability bar.

Feature groups:

UNIVERSE track:
- price and liquidity: returns over several lookbacks, volatility, max drawdown, downside volatility, volume and turnover trends, illiquidity, distance from 52-week high
- ratings: counts of actions, downgrades and negative watches/outlooks, the current rating bucket, time since the last downgrade
- prior SEBI orders and prior IBBI-related mentions, via auto-links

SEED track (15 companies, descriptive only):
- the full governance event features with their tier (VERIFIED or CANDIDATE) shown
- pledge level and change from structured numbers
- auditor changes, KMP and ID exits, audit qualifications, RPT growth, result delays
- guidance credibility (§5)

Financial features:
- Attempt span-cited extraction of revenue, receivables, CFO and PAT from the seed annual reports.
- Use them ONLY if the span-verification pass rate on a checked sample is at least 90%; otherwise exclude them and say why.
- State that broad-universe ratios (Altman Z, receivables days) are not computable without licensed or exchange financial data.

## 5. GUIDANCE EXTRACTION AND GUIDANCE_MISS (seed track)

1. Extract quantitative forward-looking statements from seed transcripts and annual reports:
   - metric, value or range, unit, target period, speaker role if stated, statement date
   - a span citation, verified against raw_text
   Qualitative statements are recorded as such.
2. Match each statement to the later-reported actual for the same metric and period. The actual's known_at must be after the statement.
3. GUIDANCE_MISS: per the taxonomy v1.0 rule, with the tolerance defined per metric type and boundary tests.
4. Management-credibility series: misses over evaluable guidance, point-in-time and rolling.
5. Evaluate on a silver sample labelled SILVER-UNREVIEWED, and add those items to the Phase 6 review queue. Report "insufficient data" honestly where it applies.

## 6. MODELS (UNIVERSE track, primary outcome first)

Baselines:
- B0: base rate
- B1: rating-only rule
- B2: logistic regression on price and liquidity features
- B3: logistic regression on all STRUCTURED + RULE-VERIFIED features

Main model, LightGBM:
- explicit regularisation (num_leaves, min_data_in_leaf, feature_fraction, lambda_l1/l2, early stopping on the validation fold)
- imbalance handling: compare scale_pos_weight versus none, and choose on validation
- deterministic seeds
- tuning on inner validation folds only, with a small documented search space

Calibration:
- isotonic ONLY if the calibration fold has at least 50 positives; otherwise Platt scaling, or uncalibrated with the reason
- always produce a reliability diagram

Interpretability: SHAP TreeExplainer, global importance plus per-prediction top contributors, stored with the scores.

Seed track: no predictive claims. Per-company point-in-time timelines of events (tier shown), features, credibility and outcomes.

## 7. WALK-FORWARD EVALUATION AND LEAKAGE CONTROLS

Walk-forward:
- expanding-window, yearly outer folds
- train on as_of < T − H − embargo
- test on as_of in [T, T+1y)
- embargo at least 12 months
- print the fold table: dates, companies, observations, positives

Metrics per fold and pooled, each with counts:
- PR-AUC versus prevalence
- ROC-AUC (secondary)
- precision@K (top 1%; top 50 per month)
- recall at a fixed alert rate
- Brier score and Brier skill score versus base rate
- ECE plus the reliability diagram
- lead time: median days from the first alert above threshold to the outcome, for true positives

Uncertainty:
- company-clustered bootstrap 95% intervals on the key metrics
- if pooled positives are below 30, state that the results are statistically inconclusive and claim no predictive skill

Leakage checks, as automated tests AND a report:
- max_input_known_at <= as_of for every snapshot
- outcome date > as_of for every label
- time-ordered folds with the embargo enforced
- label-permutation test: performance roughly at prevalence
- feature-shift test: shifting features forward must make performance worse; investigate if it improves
- flags for any feature with univariate PR-AUC near 1.0
- a deliberately leaky synthetic feature must be caught: prove it

Survivorship: report metrics with and without later-delisted companies, and the companies and observations lost.

Data-quality report:
- missingness by feature and year
- rating and IBBI coverage over time
- entity-link exclusions
- bhavcopy gaps

Ablation:
- (a) STRUCTURED
- (b) + RULE-VERIFIED
- (c) + EVENT-CANDIDATE (unverified)
Report the deltas with intervals. If (c) adds nothing measurable, or hurts, say so.

## 8. SCORING AND STORAGE

Migrations:
- scores: company_id, as_of, model name and version, calibrated and raw probability, percentile, top SHAP contributors, feature_set_version, outcome spec hash
- experiments: config, data snapshot hashes, git SHA, metrics, artifacts URI

Additional rules:
- Model artifacts go to Garage with sha256 recorded in model_registry. Artifacts are gitignored.
- get_score(company, as_of) returns only scores computed from snapshots at or before as_of. Test it.

## 9. PIPELINE AND COMMANDS

- Dagster assets: outcomes → feature_snapshots → train (manual) → score (monthly schedule) → reports. Idempotent per version.
- Commands:
  - backfill-universe
  - outcomes-build
  - features-build
  - guidance-extract, guidance-match
  - train-risk
  - backtest
  - leakage-check
  - ablation
  - score
  - model-card
- Re-running backtest on the same snapshot gives identical metrics. Show the diff.

## 10. TESTS

Unit tests:
- the detector evidence requirements and boilerplate suppression, using gold-derived dev fixtures
- the gold-only selection logic
- outcome rules and censoring
- every feature's as_of correctness, including the known_at edge cases (same-day, timezone, late-published documents)
- the embargo and fold construction
- the GUIDANCE_MISS boundaries
- the calibration choice rule
- get_score point-in-time behaviour
- the frozen-split guard
- the feature-policy guard: the primary model rejects EVENT-CANDIDATE features

Integration test: the end-to-end pipeline on a small real slice.

Leakage tests: the deliberately leaky feature is caught.

No placeholder tests.

## 11. DOCUMENTATION

- docs/modelling/event-reliability.md
- docs/modelling/outcomes.md
- docs/modelling/features.md (generated)
- docs/modelling/guidance.md
- docs/modelling/evaluation-protocol.md
- docs/modelling/data-quality.md
- docs/modelling/model-card.md:
  - intended use, not investment advice
  - data, outcomes and metrics with intervals
  - calibration
  - coverage limits
  - silver-label error rates and the event reliability tiers
  - failure modes
  - ethical considerations
- docs/experiments/<id>.md (auto-generated)
- docs/adr/0006-risk-modelling.md
- docs/release/release-gates.md (updated)
- README phase status
- docs/phase-3/phase-3-report.md

## 12. RUN AND VERIFY

Run, recording raw output:
1. lint, typecheck
2. all tests
3. migrations from empty
4. the §1 hardening evaluation
5. backfill-universe (with its progress)
6. outcomes-build
7. features-build
8. guidance-extract and guidance-match
9. backtest
10. leakage-check
11. ablation
12. score
13. model-card
14. pre-commit run --all-files
15. a full-history gitleaks scan

## 13. COMMIT (LOCAL ONLY) AND BACKUP

Commits:
- "phase-2:" prefix for the §1 hardening; "phase-3:" prefix for everything else. Use the existing identity; do not change git config.
- ABSOLUTE RESTRICTION: do not add Claude, Claude Code, Anthropic or any AI agent as contributor, collaborator, co-author, GitHub App, bot or repository member. No Co-Authored-By trailer, no "Generated with" line, no AI attribution of any kind.
- Verify with: git log -n 12 --format='%H%n%an <%ae>%n%B---'

No remote, no push.

Backup:
- git bundle create ../ledgerlight-backups/ledgerlight-phase-3.bundle --all
- git bundle verify on it

## 14. EXIT GATES

1. The test split and gold labels are frozen with a guard. Selection uses gold validation only. Detectors are hardened, with before/after gold-validation metrics and a single final test report. The event reliability tiers are documented.
2. Universe data is expanded within compliance. Entity-link rates are reported. Only auto-links are used.
3. Outcomes are frozen and hashed before training, with censoring handled, evidence spans, and the outcome-evidence review file plus its release gate.
4. 100% of feature rows have max_input_known_at <= as_of (proven by test and query). The universe includes later-delisted companies. The feature policy is enforced.
5. Guidance extraction and matching work with span verification. GUIDANCE_MISS boundaries are tested. The credibility series is produced, or limits are stated.
6. B0–B3 and LightGBM are evaluated walk-forward with an embargo of at least 12 months, with all §7 metrics, counts and intervals.
7. The calibration choice is justified. A reliability diagram is produced. SHAP is stored.
8. All leakage checks pass, including catching the leaky feature. Permutation, shift and survivorship results are reported.
9. The ablation is reported, including null or negative results.
10. The model card and experiment reports are complete. Results are labelled inconclusive where the positive counts require it.
11. Backtest reproducibility is proven. All tests and checks pass. The secret scan is clean.
12. Committed locally with no AI attribution. The bundle is verified. Nothing pushed.

## 15. FINAL REPORT

Print in full, and save to docs/phase-3/phase-3-report.md:
1. Summary
2. Files changed
3. Commands run
4. Raw test and check results
5. §1 selection-fix and hardening results (before/after, the test report, the reliability tiers)
6. Data expansion and entity-link rates
7. Outcome spec, hash and outcome counts by year
8. Fold table
9. Metrics tables with counts and intervals
10. Calibration and SHAP summary
11. Leakage, permutation, shift and survivorship results
12. Ablation
13. Guidance and credibility results
14. Data-quality summary
15. Silver and unverified dependencies
16. Limitations and defects
17. Decisions needing my approval
18. Git SHAs, identity, the trailer check, and the bundle verify output
19. Exit-gate checklist with evidence

Paste raw command output wherever evidence is cited; summaries alone are not evidence.

Stop after Phase 3. Do not begin Phase 4.

---

## Addendum (2026-10-28): PHASE 3 CONTINUATION (§1 close-out, then §2 onward)

§1 is done. Continue Phase 3 from the original Phase 3 brief. All of its ground rules, the feature policy, the exit gates and the git rules (local commits only, no AI attribution, bundle at the end) still apply.

### A. CLOSE OUT §1 (print raw evidence)

1. Name the exact gold items (IDs and split) that informed each hardening change.
   If ANY frozen-TEST item informed a change:
   - state it plainly
   - mark the test metrics as "test split consulted during development — not held-out" in event-reliability.md and the reports
   - do not hide or re-split it
2. Print the per-type precision, recall and support with intervals on GOLD VALIDATION, before versus after hardening. Then print the single final test report.
3. Print the estimated stored-event false-positive counts per type after hardening, and the event counts by type, status and tier.

### B. MAKE THE BRIEF DURABLE ACROSS SESSIONS

- If you still have the full Phase 3 brief in context, save it verbatim to docs/phase-3/brief.md and commit it.
- Maintain docs/phase-3/progress.md: sections done, sections in progress, the exact next step, the commands to resume any long-running job, and open defects. Update it at every checkpoint and before you stop.
- At the start of any later session: read brief.md and progress.md first, then resume.

### C. CONTINUE §2 → §15 IN ORDER

- Start the long bhavcopy backfill (§2.1) as a background or resumable job early, and work on §2.2–§5 while it runs. Report its progress honestly.
- Freeze the outcome spec (§3) before any training code runs.
- Commit at each completed section with a "phase-3:" prefix, after its tests pass.
- Keep going until Phase 3 is complete or you hit a genuine blocker. If you must stop for session limits:
  - update progress.md
  - commit
  - refresh the bundle
  - report exactly where you stopped
  Do not skip sections, fake results or weaken any exit gate to finish faster.
- When finished: produce the full §15 final report with raw command output, re-mark all §14 exit gates with evidence, and stop. Do not begin Phase 4.
