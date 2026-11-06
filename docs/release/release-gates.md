# Release Gates

Tracks known gaps that block (or partially block) treating Ledgerlight's
output as release-ready, independent of the per-phase exit-gate tables
in each phase report. A gap listed here stays listed until the work
that closes it actually lands -- this file is not a status dashboard
that gets marked "done" on a promise.

## Gap: no review infrastructure for field/entity-pair/retrieval-query gold labels

**Status: PARTIALLY CLOSED (2026-11-06, Phase 6A §7).** The tools now
exist: `scripts/field_review.py`, `scripts/entity_pair_review.py`,
`scripts/retrieval_review.py`, `scripts/outcome_evidence_review.py`
(file-backed append-only JSONL audits under
`docs/phase-6/review-pack/`, not the originally-envisioned
`label_item_fields` DB table -- a deliberate, documented choice to
avoid a schema/migration change for what the brief treats as this
phase's own review pack, not a permanent production feature). Each
resumes after interruption, persists a skip with a note, records the
reviewer, and samples deterministically test-split-first. See
`docs/phase-6/human-review-guide.md`.

**Still open:** no human has actually reviewed anything yet through
these tools -- that is explicitly Phase 6B's job, not this phase's.
Gold evaluation for extraction/entity-resolution/retrieval therefore
remains **PENDING_HUMAN_REVIEW** (see
`docs/evaluation/final-evaluation.md`) until that happens. The entity-
pair review sample is also honestly smaller than the brief's own ~20
target (5 real pairs) -- the real corpus is too thin to support more
without inventing cases (disclosed in both the tool's own docstring
and the human-review-guide).

**Previous status (superseded):** open. **Deferred to:** Phase 6.

**What's missing:** `label_item_fields` (the table for field-level gold
review) has a schema but 0 rows -- nothing has ever written to it. There
is no table at all for labelled entity-mention-pairs or for a reviewed
retrieval-query set. Only event-level review (`label_items`, via
`scripts/label_review.py`) has ever been built or exercised.

**What this blocks:** gold evaluation for anything other than event
classification. Specifically:
- **Extraction** (exact-match/normalized-match accuracy, coverage, and
  verification-failure rate per field) has no gold field values to
  compare against, however many event-level gold labels exist.
- **Entity resolution** (pairwise precision/recall/F1 for the full
  method vs. exact-match-only) has no labelled mention-pairs, gold or
  silver, to evaluate against at all.
- **Retrieval** (Recall@5/Recall@10/MRR against a human-reviewed query
  set) currently only has an `ai_constructed_unreviewed` silver query
  set (see `docs/knowledge/retrieval.md`) -- there is no mechanism for
  a human to review or correct a retrieval query's relevance judgement.

**First seen:** Phase 2 report §17.1/§17.2 (gold-evaluation completion
pass) and §18.3 (this review-sample change). Not built as part of
either of those changes -- explicitly out of scope by instruction both
times.

**Closing this gap requires** (not built, scoped here only): a
`label_item_fields`-reviewing CLI path (currently schema-only); a
labelled-mention-pair table plus a review CLI for it; a
reviewed-retrieval-query table plus a review CLI for it. Each needs the
same silver/gold discipline as `label_items` -- `label_source`,
`reviewer`, `reviewed_at` -- and the same human-only restriction on who
may set `label_source='human_reviewed'`.

## Gap: event-level gold coverage is thin and uneven

**Status:** open, partially closed -- the 80-item sample is fully reviewed; real coverage
gaps remain where the corpus itself has no test/validation examples of a class.

The deterministic 80-item sample (`data/manifests/label-review-sample-42.jsonl`, seed 42) is
now fully reviewed: 50 accepted, 25 corrected, 2 rejected, 3 skipped (verified against the
database; see `docs/phase-2/phase-2-report.md` §19.1). This gave the `test` split its first
gold coverage (14 items: 9 `none`, 4 `AUD_RESIGN`, 1 `PLEDGE_UP`) and the `validation` split
41 gold items.

Measured silver-label error rates (§19.2 of the Phase 2 report) turned out to be real and, for
several classes, high: `ID_EXIT` 83.3%, `RPT_GROWTH` 66.7%, `PLEDGE_UP` 57.1% error, all with
real support (n>=6). `RATING_ACT` was never reviewed at all (0 items in `test`/`validation` to
pull from -- every `RATING_ACT` silver item landed in `dev`, which this sample's design
deliberately never draws new items from). `FORENSIC` similarly has 0 coverage reachable from
`test`/`validation`. `AUDIT_QUAL`, `KMP_EXIT`, `RESULT_DELAY` all remain at insufficient
support (n<5) even after this round.

**Closing this gap further requires**: acquiring more real `RATING_ACT`/`FORENSIC` corpus
documents whose silver proposals land in `test`/`validation` (no amount of review can create
coverage that doesn't exist in the corpus), and continued review to push
`AUDIT_QUAL`/`KMP_EXIT`/`RESULT_DELAY` past n=5. See
`docs/phase-2/phase-2-report.md` §19.4.2 for which event types are and aren't recommended as
reliable enough for Phase 3 consumption given the error rates measured so far.

## Gap: human spot-check of primary-outcome evidence completed before release

**Status:** open. **Deferred to:** Phase 6.

**What's missing:** every positive `IBBI_CIRP_ADMISSION` and `RATING_DOWNGRADE_D` row (the
primary outcome's two trigger types, see `docs/modelling/outcomes.md` §2) is listed with its
real evidence citation in `docs/modelling/outcome-evidence-review.csv`, but no human has
reviewed any row yet -- the `reviewer_verdict`/`reviewer_name`/`review_date`/`review_notes`
columns are all blank. `IBBI_CIRP_ADMISSION` detection is a disclosed heuristic (earliest order
per normalized case number), not a hand-verified legal classification; `RATING_DOWNGRADE_D` is
span-verified text-matched, not semantically verified.

**What this blocks:** treating the primary outcome label as ground truth for model training,
walk-forward evaluation, or release reporting. Until reviewed, every `PRIMARY_DISTRESS` positive
is a candidate, not a confirmed label.

**Closing this gap requires**: a human reviewer works through
`docs/modelling/outcome-evidence-review.csv` row by row, opens each cited `retrieval_url`/page/
span, and records a verdict, their name, and the review date in the corresponding columns. Must
not be done by Claude or any other AI agent -- same human-only restriction as gold-label review
elsewhere in this project (see the gap above). Must also be re-run against any new rows produced
once the full-universe IBBI discovery crawl (Phase 3 §3) finishes and is extracted.

## Gap: GUIDANCE_MISS extraction not built -- no real guidance statements in the corpus

**Status:** limits stated (Phase 3 exit gate 5's own explicit fallback). **Deferred to:** a
future phase, contingent on acquiring a compliant guidance-statement source.

**What's missing:** `GUIDANCE_MISS` (guidance vs. actual miss) has a taxonomy definition
(`detection_approach: deferred_phase3`) but no extraction code, no events, no feature, and no
credibility series. See `docs/modelling/guidance-extraction-assessment.md` for the full
real-evidence writeup.

**Why:** searched all 4,759 real pages in the corpus (every document type, not just
`investor_presentation`) for quantitative, forward-looking, management-stated guidance
language. 64 raw keyword hits, 0 real matches -- 58 are the unrelated ICAI "Guidance Note"
auditing-standard phrase or generic CSR "career guidance" language; the other 6 are false
positives (CARE's own analyst commentary, SEBI procedural language), each checked and cited
by document/page/span in the assessment doc. This project's real document acquisition was
scoped to compliant structured/semi-structured sources (bhavcopy, CARE rationales,
NCLT/IBBI/SEBI orders) -- none of which is the natural home for forward guidance, which
lives in earnings-call transcripts and dedicated guidance press releases this project never
identified a compliant bulk source for.

**Closing this gap requires:** identifying and acquiring a compliant source of real,
quantitative, management-issued forward guidance (candidates: exchange-filed investor
presentations at scale, a compliant earnings-call-transcript archive) before any extraction
code is written -- building the machinery first, with nothing real to run it against, was
explicitly rejected (see the assessment doc's "Decision" section).

## Gap: Sec6/7 primary risk model is statistically inconclusive -- no predictive-skill claim

**Status:** stated plainly, per the user's own explicit condition (2026-10-31: "if pooled
distinct positive events number fewer than 30, run everything anyway, but state that the
results are statistically inconclusive and make no claim of predictive skill"). **Deferred
to:** a future phase, contingent on a materially larger verified-coverage universe.

**What's missing:** real predictive skill. The restricted universe of companies with BOTH
real IBBI and real CARE Filing coverage is only 5 companies (DHFL, Future Retail, Gensol, Jet
Airways, SpiceJet) -- the real pooled distinct positive event count is 5, far below the
30-event floor. No model variant (B0 base rate, B1 rating rule, B2/B3 logistic, LightGBM)
beats the training-fold base rate pooled across walk-forward folds; every Brier skill score
is negative. See `docs/modelling/model-card.md` (generated) and `scripts/backtest.py`'s real
output for the full numbers, with company-clustered bootstrap intervals.

**What this blocks:** using any score this pipeline produces for a real decision of any kind.
`scripts/score.py`'s own docstring and `docs/modelling/model-card.md`'s "Intended use" section
both state this is not investment advice.

**Also disclosed, not hidden:** (1) the Sec7 feature-shift leakage test shows shifted PR-AUC
higher than unshifted, attributable to long same-episode label runs in this tiny dataset
rather than a demonstrated leak; (2) the univariate PR-AUC flag catches
`days_since_last_downgrade` at 1.0 in the real data; (3) `scripts/score.py`'s deployment-time
imputation and calibration are simplified relative to training time, since persisting the
exact training-time medians and the per-fold calibration map was not built given there is no
real predictive signal at stake either way; (4) SpiceJet's original Phase 0 role as a "no
known distress" control company is now known to be questionable (8 real NCLT petitions found
against it, 2021-2026) -- not resolved unilaterally, flagged for human review.

**Closing this gap requires:** a materially larger real verified-coverage universe (more
companies with both real IBBI and real CARE Filing coverage) before any predictive-skill
claim can be made, plus a human decision on SpiceJet's control-group status.

## Gap: no human review of investigation agent dossiers has ever happened

**Status:** open, by explicit instruction. **Deferred to:** Phase 6, per the Phase 4
brief's own §8 text: "Human quality evaluation DEFERRED to Phase 6."

**What's missing:** every real dossier the Phase 4 investigation agent produces has been
checked by the automated verifier (`docs/agent/verifier.md`) and, where §9's adversarial
tests apply, by a synthetic/mocked scenario -- but no real human has reviewed a real,
FINALISED dossier's prose for whether it is actually correct, well-calibrated, or useful,
and no real human has worked through the `dossier-review` CLI's open queue at all. The
seeded-QC mechanism (`ledgerlight.agent.qc_seed`, `docs/agent/review-workflow.md`) exists
and is itself tested, but its real reviewer catch rate has never been measured against a
real human, since no real human review has happened.

**What this blocks:** any claim that a real dossier's prose is trustworthy beyond what the
automated verifier checks (citation resolution, dates, numbers, entailment, banned
language) -- things a verifier cannot judge, like whether a finding is actually
material, whether the chosen severity is reasonable, or whether the overall narrative is
misleading despite every individual sentence passing its own checks.

**Closing this gap requires:** a real human reviewer running `dossier-review` against at
least 10 real, FINALISED dossiers (not seeded QC items, not gold items) and recording real
decisions, plus a real `qc-seed`-seeded batch reviewed by that same human so a real catch
rate per flaw type can be reported -- both explicitly required before release, per the
brief's own instruction, added here as a standing release gate rather than left only in a
Phase 4 evaluation doc.

## Gap: GitHub Actions workflows have never run on GitHub -- UNVERIFIED until a first real push

**Status:** open, by design. **Reason:** this project's own standing GIT POLICY (every
phase since Phase 0) is commit locally only, no remote, no push -- `git remote -v` has
been empty throughout. The five real workflows under `.github/workflows/`
(`backend.yml`, `frontend.yml`, `security.yml`, `build.yml`, `deploy.yml`) were validated
the only way possible without a remote: `actionlint` (via the real, official
`rhysd/actionlint` Docker image -- clean, zero findings) and running every real job's own
commands directly on this machine (lint/typecheck/test/migrate for backend; lint/
typecheck/build/Playwright smoke for frontend; `pip-audit`/`pnpm audit`/`gitleaks`/`trivy`
for security; real `docker build` for both images) -- all passing, evidence in
`docs/phase-5/evidence/`.

**What's missing:** real execution on GitHub's own hosted runners. `actionlint` and a
local command run both verify syntax and real command correctness, but neither proves a
workflow behaves identically under GitHub's own runner environment, its own real
`GITHUB_TOKEN` permissions, its own real service-container networking, or its own real
`gitleaks-action`/`trivy-action`/`docker/build-push-action` marketplace-action versions
pulling real images at real run time.

**What this blocks:** calling any of these five workflows "CI-verified" in the sense of
"has actually run green on GitHub" -- it has not, and cannot, without a real push to a
real GitHub remote, which this project's own GIT POLICY defers until the user explicitly
provides a remote URL and confirms the policy override (tracked separately in
`docs/phase-5/progress.md`'s own "Pending items carried over" section).

**Closing this gap requires:** the user supplying a real remote URL and explicitly
confirming the GIT POLICY override, a real push, and then a real, green run of every one
of these five workflows observed directly in GitHub's own Actions tab -- not assumed from
local validation alone.

**Standing gate:** GitHub Actions runs must be verified green, directly in GitHub's own
Actions tab, after the first real push -- never assumed from `actionlint` or a local
command run, however thorough. This gate stays open until that first push happens.

## Gap: Terraform for the real AWS deployment has never been applied

**Status:** open, by design. **Reason:** no AWS credentials exist in this environment,
and applying infrastructure against a real AWS account was explicitly out of this
phase's own scope (`docs/phase-5/brief.md` §6: "not applied"). `infra/aws/` was
validated the only way possible without credentials: `terraform fmt`/`init
-backend=false`/`validate` (via the real, official `hashicorp/terraform:1.9` Docker
image -- all clean) and `tflint` (via `ghcr.io/terraform-linters/tflint:latest` --
found and fixed one real deprecated-interpolation-only-expression issue). Evidence in
`docs/phase-5/evidence/terraform-validate.log`.

**What's missing:** a real `terraform plan` against a real AWS account. `validate`
confirms the configuration is internally consistent (types, references, required
arguments); it proves nothing about what a real plan would actually propose against
real existing AWS state, real IAM permissions, or real provider-API behaviour at apply
time.

**What this blocks:** calling this Terraform "deployment-ready" in the sense of "will
apply cleanly" -- that has never been checked, and cannot be, without real AWS
credentials.

**Standing gate:** a real `terraform plan` must be generated and reviewed by a human,
line by line, BEFORE any `terraform apply` is ever run against a real AWS account --
never apply directly from `validate`-clean configuration alone, and never apply a plan
nobody has actually read. This gate stays open until a real account, credentials, and a
reviewed plan all exist together.

**Closing this gap requires:** real AWS credentials, a real `terraform plan` run against
them, a human reviewing that plan's full real diff, and only then a real `terraform
apply` -- each step distinct, none skipped.

## Gap: an optional OWASP ZAP baseline scan and the full Playwright e2e suite were not run this phase

**Status:** open, deferred by explicit user choice. **Reason:** both require the full
real stack (postgres/garage/api/worker/web) up via `docker compose`, which means
rebuilding the `api`/`web` images from scratch (removed after §5/§7's own verification)
plus running ZAP's own container and a real Playwright browser at the same time. This
session hit repeated, real host memory-pressure kills (confirmed via
`Get-CimInstance Win32_OperatingSystem`, as low as ~0.8-2.2GB free) from unrelated
running applications on this machine, not from the Docker stack itself. Asked the user
directly via `AskUserQuestion` rather than attempting a build likely to crash again;
the user chose to defer. Every other §9 security-test requirement (authorisation
matrix, cross-tenant IDOR, auth/session fixation, rate limiting, signed-URL expiry,
webhook SSRF/DNS-rebinding, prompt-injection separation, security headers) is done.

**What's missing:** a real ZAP baseline scan against the live local stack, and the full
Playwright e2e suite (login, search, overview with `as_of`, timeline, evidence view,
investigation creation, dossier view, review decision, watchlist/alert, and a denied
cross-tenant attempt) against a live backend -- `frontend/e2e/smoke.spec.ts` (§7) only
covers a minimal production-build smoke test, not this full flow.

**Closing this gap requires:** real host memory headroom (confirmed before attempting),
then rebuilding the `api`/`web` images, bringing up the full stack, and running both
tools against it.

**PARTIALLY CLOSED (2026-11-05, Phase 6A §2):** the full Playwright e2e suite now
exists and passes (`frontend/e2e/full-e2e-lite.spec.ts`, 4/4 real tests: login
through dossier/review/watchlist/alert/webhook, plus cross-tenant denial) against
the real `e2e-lite` Docker Compose profile (`docs/phase-6/evidence/
sec02-playwright-full-run.log`). Finding this test also surfaced a real, significant
CSP bug, fixed the same session -- see the dedicated gap below. The ZAP baseline
remains open; see `docs/phase-6/progress.md` for current status.

## Gap: a real, single-batch full integration-test run was not captured for §11's final evidence pass

**Status:** open, same real cause as the gap above. **Reason:** `pytest -q -m
integration` (272+ real tests against the real local stack) was attempted 3 times
during the §11 verification pass and killed each time by real host memory pressure
(as low as 1.72GB free) from the same unrelated running applications, not from the
Docker stack itself. See `docs/phase-5/evidence/sec11-backend-integration-tests.log`
for the real, honest substitute evidence: the full 272-test suite ran clean earlier
in this same phase, and every test file touched since then passed individually
against the real stack this session.

**What's missing:** one single, uninterrupted run of the complete, current
integration suite together, as one batch, with its raw output captured.

**Closing this gap requires:** real host memory headroom, then re-running `pytest -q
-m integration` as one batch and replacing the substitute evidence log with its real
output.

**CLOSED (2026-11-05, Phase 6A §1):** a real memory window opened up and the full
batch ran clean in one sequential pass -- 322 passed, 0 failed
(`docs/phase-6/evidence/sec01-green-baseline.log`). This gate is resolved.

## Gap: frontend CSP uses `'unsafe-inline'` for `script-src`, not a working nonce

**Status:** open, by design (a real, disclosed trade-off, not an oversight).
**Reason:** found while building Phase 6A §2's own first real interactive
Playwright e2e test -- the original strict `script-src 'self'` blocked Next.js's
own required inline hydration scripts outright, so the entire frontend was
non-interactive in any real CSP-enforcing browser (every form, login included,
silently fell back to a native HTML GET submission with credentials in the URL).
The documented Next.js per-request-nonce fix was implemented and tested directly;
it did not actually thread the nonce onto Next's own inline scripts in this exact
Next.js 16.4.3 App Router setup (confirmed by inspecting the raw response HTML --
no `nonce` attribute present on any inline script, even with the CSP header
itself correctly carrying one). Full writeup:
`docs/phase-6/evidence/sec02-csp-hydration-bug.md`.

**What's missing:** a working nonce-based (or hash-based) `script-src` policy that
does not require `'unsafe-inline'`.

**What this blocks:** calling this frontend's CSP "strict" -- it is not, by a real,
disclosed margin. The residual risk (an XSS injection point elsewhere executing an
injected inline script) is recorded in `docs/security/threat-model.md`; mitigating
factors already in place (no `dangerouslySetInnerHTML` anywhere, confirmed by
`tests/test_prompt_injection_separation.py`) reduce but do not eliminate this risk.

**Closing this gap requires:** real engineering time to diagnose why Next.js
16.4.3's documented nonce-propagation mechanism isn't firing in this exact
configuration (a Next.js version/config-specific investigation, not a quick fix),
or an equivalent hash-based policy with a build step that computes real per-build
script hashes.
