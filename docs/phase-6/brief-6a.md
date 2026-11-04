# LEDGERLIGHT — PHASE 6A: INTEGRATED VALIDATION, HARDENING AND REVIEW PACK (PART A of B)

Do not start until Part B arrives. Confirm receipt of Part A and wait. When Part B arrives:
1. Save both parts verbatim to docs/phase-6/brief-6a.md.
2. Create docs/phase-6/progress.md.
3. Commit both, then begin.

You are implementing Phase 6A of Ledgerlight. Phase 5 is complete on branch phase-5/api-ui-security (58 commits, local only), providing the FastAPI /v1 service, the Next.js UI, tenancy with RLS, auth and RBAC, signed URLs, webhooks, rate limits, audit logs, Docker Compose, Terraform (validated, not applied), CI workflows (validated locally) and the restore drill. Earlier phases provide ingestion, the knowledge store, entity resolution, retrieval, point-in-time features, outcomes, LightGBM scores, the investigation agent, the verifier and review.

Deferred gates now due:
- the full Playwright e2e run and the ZAP baseline (memory kills on the host)
- the human gold review for fields, entity pairs and retrieval (those review types do not exist yet)
- the outcome-evidence spot-check
- human review of at least 10 dossiers with seeded QC
- GitHub Actions verified after the first push
See docs/release/release-gates.md.

Read before changing anything:
- docs/phase-5/phase-5-report.md, docs/phase-4/phase-4-report.md, docs/phase-3/phase-3-report.md, docs/phase-2/phase-2-report.md
- docs/release/release-gates.md
- docs/modelling/*.md, docs/agent/*.md, docs/security/*.md
- docs/adr/*

Scope:
- integrated end-to-end validation, regression, reproducibility, audits
- performance, reliability and failure recovery
- security and tenant re-validation
- cost per filing, the compliance and licence review
- final documentation, the clean-install test, the readiness checklist
- BUILDING the human review pack

Do NOT:
- review anything as the human
- push, add a remote, or tag a release (that is Phase 6B)

Stop at the HUMAN CHECKPOINT (§18).

## 0. GROUND RULES

- All earlier ground rules apply:
  - no fabrication, no sudo
  - honest UA, respect robots.txt and terms
  - no secrets or raw data in git
  - neutral language and disclaimers
  - frozen test split never used for tuning
- Never weaken a gate, threshold or test to get a pass. Anything not achieved is marked PARTIAL or BLOCKED with the reason.
- The host has limited memory and other apps running. Prefer sequential execution, resource limits and low-memory profiles over skipping work.
- GIT POLICY: commit locally only. No remote, no push, no tags.

## 1. PREFLIGHT: CONSOLIDATED EVIDENCE FILE (stop conditions)

1. Branch phase-6/integrated-validation-release from the Phase 5 HEAD. Run the full checks and record a green baseline.
2. Create docs/phase-6/orchestrator-evidence.md and fill it with VERBATIM copies (raw tables and outputs, not summaries) of:
   - Phase 2: the silver error rates, the gold test metrics, the selection fix
   - Phase 3:
     - the §1 hardening before/after on gold validation, and whether any frozen TEST items informed it (with the resulting held-out labelling)
     - the fold table with DISTINCT positive events and companies
     - the metrics versus the B0 base rate with intervals
     - calibration
     - leakage, permutation, shift and survivorship results
     - the ablation
     - the rating-only and IBBI-only sensitivity
   - Phase 4:
     - one full example dossier
     - the evaluation tables
     - the adversarial results
     - the verifier-fix diffs plus the tests proving that a wrong-date rating claim and a wrong timeline_entry still FAIL
     - review_tasks counts by reason code, and the count of dossiers relying mainly on CANDIDATE events
   - Phase 5:
     - the authorisation matrix results
     - the RLS and cross-tenant results
     - the dependency and container scan triage
     - the actionlint and per-job local results
     - the restore drill output
     - the list of deferred items
   - current release-gates.md
   Commit it.
3. STOP and report, without continuing, if ANY of the following holds:
   - a wrong-date rating claim or a wrong timeline_entry passes verification
   - CANDIDATE-reliant dossiers did not create review tasks
   - any leakage check failed
   - frozen TEST items informed hardening but the metrics are labelled held-out
   - any cross-tenant read or write succeeded

## 2. LOW-MEMORY STACK PROFILE AND THE DEFERRED E2E/ZAP RUNS

1. Measure the memory use of each compose service at idle and under the e2e load. Print the numbers.
2. Add a compose profile (or override file) "e2e-lite":
   - per-service memory limits
   - the Dagster webserver off unless needed
   - worker concurrency set to 1
   - Postgres tuned (shared_buffers, work_mem) for a small host
   - models loaded lazily
   - services started in order with healthchecks
   Document the PowerShell commands to run it.
3. Run the FULL Playwright e2e suite on e2e-lite:
   - log in, search, overview with as_of, timeline with tiers, open evidence with the highlighted span
   - start an investigation, view the dossier, review a task
   - create a watchlist, trigger an alert and webhook delivery
   - a cross-tenant attempt is denied
   Save traces and screenshots under docs/phase-6/evidence/.
4. Run the OWASP ZAP baseline against the e2e-lite stack (container, no sudo). Triage every finding: fixed, or accepted with justification.
5. If memory kills still occur:
   - record the exact OOM evidence and the service affected
   - try a further reduction, e.g. running the UI tests against api + web + postgres + garage only, with the worker run separately
   Mark a gate BLOCKED only after these attempts, with the evidence.

## 3. END-TO-END PIPELINE TEST (ingestion → dossier)

Write an automated E2E test, plus a reproducible script, that runs:
1. drop a real seed document plus a provenance row into data/inbox, and run import-local
2. Dagster processing: storage, pages, OCR if needed
3. chunk, embed, classify, extract, verify
4. events with tier
5. entity links
6. feature snapshot and score (get_score at as_of)
7. investigation and dossier, verified
8. review task routing
9. alert rule firing and the signed webhook delivery
10. the API and UI showing the result

Assert the provenance and known_at chain end to end: every dossier citation resolves to the stored page span of the ingested version. Run it twice to prove idempotency.

## 4. REGRESSION SUITE

- Golden-snapshot regression tests over a fixed real subset, covering:
  - extraction outputs
  - event sets and tiers
  - entity links
  - feature values at fixed as_of dates
  - score values for a frozen model artifact
  - dossier hashes (offline renderer)
- Any change requires an explicit, documented snapshot update. Add a single test-regression command.
- Run the complete test pyramid (unit, integration, corpus, e2e, security) and print counts per layer.

## 5. BACKTEST REPRODUCIBILITY AND AUDITS

1. From a clean database restore (or rebuild), re-run outcomes-build, features-build and backtest with the frozen model config and spec hashes. Diff the metrics against the Phase 3 report: they must be identical, or every difference explained.
2. Re-run the leakage, permutation, feature-shift and survivorship audits, plus the point-in-time proof query. Print the results.
3. Confirm the outcome spec hash, feature_set_version and model artifact hashes all match model_registry.

## 6. CONSOLIDATED EVALUATION REPORT (pre-review)

Write docs/evaluation/final-evaluation.md, with each section marked GOLD, SILVER-UNREVIEWED or SYNTHETIC, and support counts and intervals throughout:
- classification
- extraction (silver for now)
- entity resolution (silver for now)
- retrieval (silver for now)
- citation and verifier (adversarial plus agent-eval)
- the risk model (backtest)
Sections waiting on the human review are marked PENDING_HUMAN_REVIEW, to be finalised in 6B.

(END OF PART A — wait for Part B)

# LEDGERLIGHT — PHASE 6A BRIEF (PART B of B)

## 7. HUMAN REVIEW PACK (build the tools; do NOT review)

Build the missing review types and one combined pack. Every type must:
- run via both a make target and a Windows PowerShell .venv command
- resume after interruption
- persist skip with a note
- write an append-only audit
- record the reviewer name
- use deterministic samples drawn test-split-first, with validation top-up tagged

Review types:
1. Field review: about 30 extracted fields across event types. Show the value, the cited span and the context. Decisions: correct / wrong-value / unsupported / skip, with the corrected value.
2. Entity-pair review: about 20 mention pairs, including near-threshold matches. Decisions: same / different / unsure.
3. Retrieval review: about 10 queries × top-10 hybrid results. Mark each result relevant or not.
4. Outcome-evidence spot-check: every positive primary-outcome event if 60 or fewer, otherwise a stratified sample of 60 (IBBI versus rating-default, by year). Decision: evidence supports the outcome (yes / no / unclear) and the date is correct (yes / no).
5. Dossier review: at least 10 real dossiers (mixed seed and universe, high and low score), plus about 3 seeded-QC flawed dossiers mixed in, unlabelled to the reviewer. Uses the existing dossier-review flow.

Then write docs/phase-6/human-review-guide.md:
- the order to do things in, with the commands
- time estimates per type
- clear decision rules with 1–2 examples each
- a one-page summary

Also: a review-progress command that shows counts per type and per reviewer.

## 8. PERFORMANCE AND RELIABILITY (within host limits)

Performance:
- An API load test (k6 or locust, small scale suited to the host) on the key read endpoints. Report p50, p95 and p99 latency, the error rate and the request rate, and state the host specification.
- Ingestion and processing throughput (documents/minute, pages/minute), per stage.
- Agent runtime p50/p95 (from agent-eval).

Failure recovery, each demonstrated with before/after evidence:
- kill the worker mid-ingestion, then resume with no duplicates
- restart Postgres during API traffic: clean errors, then recovery
- Garage unavailable: retries, dead letters, then reprocess
- crash the agent mid-run, then resume from checkpoint
- an expired session and a revoked API key mid-use

## 9. SECURITY AND TENANT RE-VALIDATION

Re-run, on the final code:
- the authorisation matrix
- RLS and API cross-tenant tests, including IDOR
- auth, CSRF and session tests
- signed URL expiry
- webhook SSRF and signature tests
- rate limits
- the prompt-injection and escaping tests
- the security headers
- pip-audit, pnpm audit, trivy on all images, and a full-history gitleaks scan
Triage every finding.

Update docs/security/threat-model.md with residual risks.

## 10. COST PER FILING

Measure per stage, per filing (mean and p95): CPU seconds, peak memory, wall time, storage bytes (raw plus derived), embedding and NLI inference time, and LLM tokens and cost (0 if the offline renderer was used).

Produce:
- docs/ops/cost-per-filing.md: measured local resource use
- a parameterised AWS cost model:
  - uses current public prices ONLY if you can cite the AWS pricing page with an access date
  - otherwise leaves prices as clearly marked inputs
  - shows the formula and an example scenario (e.g., 10k filings/month)
  - never invents prices

## 11. DATA-SOURCE COMPLIANCE AND LICENCE REVIEW

1. Re-check robots.txt and the terms for every enabled source (date-stamped). Record any changes since Phase 0.
2. Write docs/compliance/data-sources.md with, per source:
   - access basis, storage and redistribution status
   - what the repository contains (metadata only versus content)
   - what a deployed product could legally show
3. Third-party licence inventory for Python and npm dependencies, model checkpoints and container images. Use pip-licenses, license-checker or equivalent. Flag copyleft or unclear licences.
4. Add to the docs: a statement that commercial use requires legal review and licensed exchange data. Keep the CRISIL and BSE/NSE BLOCKED status explicit.

## 12. FINAL DOCUMENTATION

Complete and reconcile with the implementation:
- docs/architecture.md: the system overview with Mermaid diagrams (data flow, components, deployment)
- docs/data-dictionary.md: every table and column, generated from the models and migrations, with time-field semantics
- docs/api/: the OpenAPI export plus a usage guide
- docs/deploy/: local Windows setup, Docker Compose, the AWS guide
- docs/modelling/model-card.md: final, with GOLD, SILVER and SYNTHETIC markers and limitations
- the ops runbooks
- the README: what Ledgerlight is, honest results, limitations, quick start, the phase summary

No document may claim more than the evidence supports.

## 13. CLEAN-INSTALL AND REPRODUCIBLE-SETUP TEST

1. Clone the repository from the latest bundle into a NEW directory (e.g., ../ledgerlight-clean-test).
2. Follow ONLY the README and the docs, using PowerShell commands, to:
   - set up the environment
   - start the stack
   - run migrations
   - load sample data (via documented acquisition or import, not copied DB files)
   - run the tests
   - open the UI
3. Record every step, its time, and every doc defect found. Fix the docs and repeat until a clean run succeeds.
4. Then delete the test directory.

## 14. PRODUCTION-READINESS CHECKLIST

Write docs/release/production-readiness.md. Mark every capability from the master requirements COMPLETE, PARTIAL or BLOCKED, with evidence links and the reason. Include at minimum:
- data access (BSE/NSE blocked)
- the gold review status
- predictive validity (inconclusive or not)
- financial features (excluded)
- guidance (no data)
- GitHub CI (unverified until push)
- AWS (not deployed)
- the legal and licensing status

## 15. RELEASE-GATE STATUS

Evaluate every gate in release-gates.md: PASS, PENDING_HUMAN_REVIEW, PENDING_PUSH or BLOCKED, with evidence. The human and push gates are expected to be pending at this point.

## 16. RUN AND VERIFY

Run, recording raw output:
- all test layers, test-regression and the e2e pipeline test (twice)
- Playwright on e2e-lite and the ZAP baseline
- the backtest reproducibility diff and the audits
- the load test and the failure-recovery drills
- the security suite and the scans
- the licence inventory
- the clean-install run
- pre-commit run --all-files and a full-history gitleaks scan

## 17. COMMIT (LOCAL ONLY) AND BACKUP

Commits:
- "phase-6:" prefixed messages, using the existing identity. Do not change git config.
- ABSOLUTE RESTRICTION: do not add Claude, Claude Code, Anthropic or any AI agent as contributor, collaborator, co-author, GitHub App, bot or repository member. No Co-Authored-By trailer, no "Generated with" line, no AI attribution of any kind.
- Verify with: git log -n 10 --format='%H%n%an <%ae>%n%B---'

No remote, no push, no tags.

Backup:
- git bundle create ../ledgerlight-backups/ledgerlight-phase-6a.bundle --all
- git bundle verify on it

## 18. HUMAN CHECKPOINT AND 6A EXIT GATES

6A exit gates:
1. orchestrator-evidence.md is complete and no stop condition was triggered.
2. The Playwright e2e and ZAP runs are complete on e2e-lite, or BLOCKED with OOM evidence after the reduction attempts.
3. The E2E ingestion-to-dossier test passes twice. The citation chain is proven.
4. The regression suite is in place. All test layers pass.
5. The backtest is reproduced with the diff shown. The audits are re-run and pass.
6. Performance and failure-recovery results are reported.
7. Security and tenant re-validation pass. All findings are triaged.
8. Cost per filing is measured. The cost model contains no invented prices.
9. The compliance and licence review is complete.
10. The final docs are complete. The clean install succeeded from the docs alone.
11. The readiness checklist and release-gate status are written.
12. All five review types are built and tested. The guide and progress command work.
13. Committed locally with no AI attribution. The bundle is verified.

Final report: print in full and save to docs/phase-6/phase-6a-report.md:
- every section's raw evidence
- the gate checklist
- limitations
- decisions needing my approval
- git SHAs, identity, the trailer check, the bundle verify output

Then STOP and print:
"HUMAN CHECKPOINT: run the review pack per docs/phase-6/human-review-guide.md", followed by the exact commands and the per-type item counts.

Do NOT begin Phase 6B.
