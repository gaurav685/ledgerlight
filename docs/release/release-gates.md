# Release Gates

Tracks known gaps that block (or partially block) treating Ledgerlight's
output as release-ready, independent of the per-phase exit-gate tables
in each phase report. A gap listed here stays listed until the work
that closes it actually lands -- this file is not a status dashboard
that gets marked "done" on a promise.

## Gate status (Phase 6A §15, evaluated 2026-11-06)

Every gap below, evaluated against this phase's own four real outcome
categories: **PASS** (no longer actually blocking -- re-assessed, not
closed by force), **PENDING_HUMAN_REVIEW** (needs a specific human
action, explicitly deferred to Phase 6B), **PENDING_PUSH** (needs this
project's standing no-remote/no-push GIT POLICY to be lifted, a
decision for later, not this phase), or **BLOCKED** (needs something
else -- real data that doesn't exist yet, real host resources, a real
external decision -- before it can close). None of these are forced
to PASS; per the brief's own framing, the human and push gates are
*expected* to be pending at this point, and most of the rest are
expected to stay BLOCKED.

| Gate | Status | Why |
|---|---|---|
| Review infra for field/entity-pair/retrieval-query labels | PENDING_HUMAN_REVIEW | Tooling built this phase; actual review is Phase 6B's job. |
| Event-level gold coverage thin/uneven | BLOCKED | `RATING_ACT`/`FORENSIC` have zero real corpus examples reachable from `test`/`validation` -- no amount of review manufactures coverage that doesn't exist. |
| Human spot-check of primary-outcome evidence | PENDING_HUMAN_REVIEW | Sample built (`docs/modelling/outcome-evidence-review.csv`); explicitly deferred to Phase 6B. |
| GUIDANCE_MISS extraction | BLOCKED | 0 real guidance statements exist anywhere in the corpus; nothing to build against. |
| Risk model statistically inconclusive | BLOCKED | Only 5 real pooled distinct positive events exist in the verified-coverage universe -- below the 30-event floor; closing this needs more real distress events to occur over time, not more engineering. |
| No human review of agent dossiers | PENDING_HUMAN_REVIEW | Review pack built this phase; review itself is Phase 6B's job. |
| GitHub Actions never run on GitHub | PENDING_PUSH | Validated locally; genuinely unverifiable until a first real push, which GIT POLICY defers. |
| AWS Terraform never applied | BLOCKED | No AWS credentials in this environment; applying infra is out of scope for this phase. |
| ZAP baseline + full Playwright e2e not run | **PASS** (closed §2; corrected 2026-11-07, was stale) | Both actually ran against the real e2e-lite stack: Playwright 4/4, ZAP 0 FAIL/2 real findings fixed/4 accepted. This row was itself found stale while finalizing §18 and corrected here. |
| Single-batch full integration run not captured | BLOCKED | Same real memory constraint -- the batched-run result is equally valid evidence, just not a single-pass one. |
| Frontend CSP `unsafe-inline` | BLOCKED | A real Next.js 16.4.3 hydration-script limitation found this phase; the strict nonce-based policy doesn't yet work in this exact setup. |
| Deployed Docker images predate dependency fix | BLOCKED | Rebuild attempted twice, killed twice by real host memory pressure; the fix exists in `pyproject.toml`/`uv.lock`, just not baked into the running image yet. |
| `pymupdf` AGPL-3.0/commercial licence | **PASS** (closed, Phase 6 Correction 2 §5, 2026-11-12) | Resolved by licensing this whole project AGPL-3.0-or-later (`LICENSE`), not an Artifex licence or a library swap. See the gap section below. |
| 363 real corpus pages trip the OCR tripwire | BLOCKED | Not yet run through the real OCR path and spot-checked -- flagged, not investigated further this phase (outside §11's own scope). |
| Real "0 filings" bug drops filings from FINALISED dossiers | **PASS** (closed, Phase 6 Correction 1 §2, 2026-11-07) | Root cause confirmed (stale pre-fix investigations, never re-run); all 13 real dossiers re-ran clean; new permanent independent-count regression guard added. See the gap section below. |
| Dossier template's "Intended use" markdown bleed | **PASS** (closed, Phase 6 Correction 1 §3, 2026-11-07) | `export_dossier_markdown` now quotes multiline content properly; a real heading-hierarchy structure test added. See the gap section below. |
| `days_since_last_downgrade` univariate PR-AUC flag at 1.0 | **PASS** (investigated, confirmed NOT a leak, Phase 6 Correction 2 §1, 2026-11-12) | Real traced evidence rules out circular self-reference; confirmed a single-company (FRETAIL) null-pattern autocorrelation artifact, not a temporal leak. See the gap section below. |
| Review routing never fired on real high-severity findings | **PASS** (closed, Phase 6 Correction 2 §2, 2026-11-12) | Severity never threaded through outcome-context event claims, and metric claims (default-grade ratings) were structurally invisible to the routing check. Both fixed; real backfill created 58 new review tasks. See the gap section below. |
| Dossier rendering: "Unknown company" / raw UTC dates in prose | **PASS** (closed, Phase 6 Correction 2 §3, 2026-11-12) | Company name now resolved via the real `filings` link; prose dates render as Asia/Kolkata calendar dates. See the gap section below. |

**7 of 18 gates evaluate to PASS** (ZAP/Playwright, corrected
2026-11-07 above -- genuinely closed in §2; the real "0 filings" bug
and the "Intended use" markdown bleed, both closed in Phase 6
Correction 1; the `pymupdf` licence, the univariate leak
investigation, the review-routing fix, and the dossier-rendering
fixes, all closed in Phase 6 Correction 2). The other 12 stay open as
the brief's own framing anticipated -- not a sign anything here was
softened to look better than it is.

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
`days_since_last_downgrade` at 1.0 in the real data -- investigated with real traced evidence
(Phase 6 Correction 2 §1) and confirmed NOT a temporal leak, a single-company (FRETAIL)
null-pattern autocorrelation artifact instead; see the gap section below; (3) `scripts/score.py`'s deployment-time
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

**Note (Phase 6 Correction 1 §1, 2026-11-07):** the Phase 6B review
pack WAS run, but by an AI session under an explicit, bounded user
override -- it is real QA, never gold, and does not close this gate.
Every decision from that pass is quarantined (reviewer re-tagged
`"ai-qa-review"`, excluded from all gold metrics) -- see
`docs/phase-6/phase-6-correction-1.md` §1 and
`docs/phase-6/phase-6b-review-findings.md`'s own caveat. This gate
stays genuinely open until a real human runs `dossier-review`.

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

**CLOSED (2026-11-05, Phase 6A §2):** the full Playwright e2e suite now
exists and passes (`frontend/e2e/full-e2e-lite.spec.ts`, 4/4 real tests: login
through dossier/review/watchlist/alert/webhook, plus cross-tenant denial) against
the real `e2e-lite` Docker Compose profile (`docs/phase-6/evidence/
sec02-playwright-full-run.log`). Finding this test also surfaced a real, significant
CSP bug, fixed the same session -- see the dedicated gap below. **The ZAP baseline
was also run** the same session, against the real e2e-lite stack: 0 FAIL in both of
2 runs; 2 real findings fixed (`X-Powered-By` disabled, a real `Permissions-Policy`
header added), confirmed gone in a second run (6 WARN/62 PASS -> 4 WARN/64 PASS);
remaining 4 triaged as accepted (`docs/phase-6/evidence/sec02-zap-triage.md`) --
the CSP `'unsafe-inline'` trade-off (already disclosed) and 3 informational/
not-applicable findings. Playwright re-confirmed 4/4 after the header fixes. This
gate is fully closed, not partially -- the original gate text above is kept for
history; this note is the current, accurate status.

**Not re-run again in Phase 6 Correction 2 (2026-11-12), by explicit user
choice.** `infra/docker-compose.e2e-lite.yml` is an override on the SAME
project/ports as this session's live, currently-running dev Postgres (holding
every real investigation/claim/dossier this whole phase has worked against) --
running it means tearing that container down and recreating it, mid
verification pass. Correction 2 §3's dossier-rendering fix (company name,
IST dates) is user-facing, so a fresh e2e check has real value; asked the
user directly rather than assuming, and they chose not to disrupt the live
stack. The real coverage used instead: the backend render/export/verifier
test suites (`docs/phase-6/evidence/sec3-dossier-rendering-fixes.md`, 92
passed) plus a fresh real `agent-eval` run (60 investigations, 0 leakage),
both exercising the exact same rendering code path the frontend displays.
The last real Playwright result (4/4, above) still stands, unchanged by
this phase's backend-only fixes.

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

**Update (2026-11-07, Phase 6A §16):** still not closed in the strict literal
sense -- one single uninterrupted invocation covering every integration test was
not achieved. **Full functional coverage was achieved instead**: all 51 integration
files ran and passed, split across 4 batches (14+7+11+12+... see
`docs/phase-6/progress.md` §16) plus 7 files isolated individually after one
specific 7-file grouping was killed 6 times by the same real, sustained host
memory pressure (root-caused: one of those 7, `test_company_dedup.py`, genuinely
takes ~11 minutes alone, and grouping it with others stretched the batch's
exposure window to this host's own independent memory spikes). Same real
instability pattern as this gap's own original cause -- not newly introduced,
not hidden.

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

## Gap: deployed Docker images predate a real dependency security fix

**Status: open.** **First seen:** Phase 6A §9 (2026-11-06).

**What's missing:** `cryptography`/`fastapi`/`starlette`/`pytest` were bumped in
`pyproject.toml`/`uv.lock` this phase to close 24 real `pip-audit` findings (now
0). The host's own Python environment and the full test suite (408 default + 330
integration, all passing) already reflect the fix. The real `ledgerlight-phase0-api`
and `ledgerlight-phase0-web` Docker images do not -- they were built before this
change, so a fresh `trivy image` scan of either still reports the old, vulnerable
`cryptography 44.0.3`/`starlette 0.48.0`
(`docs/phase-6/evidence/sec09-trivy-api-before-rebuild.log`,
`sec09-trivy-web-before-rebuild.log`).

**What this blocks:** calling the *deployed* artifact's dependency set clean --
only the host dev environment is currently clean, not what `docker compose up`
actually runs.

**Why it's not closed:** rebuilding `api` (and the shared base image `web` also
uses) was attempted twice this phase and killed both times by this host's own
real, severe memory pressure -- the same documented pattern as §2's CSP-fix
rebuild struggles. Never forced through or silently skipped; marked BLOCKED with
the real evidence instead.

**Closing this gap requires:** `docker compose build api web` (or equivalent) on
a host with enough free memory to sustain it, then a fresh `trivy image` scan on
both images to confirm the Python-level findings are gone (the real, currently
un-patchable Debian OS-package findings and the `web` image's bundled-Node
`undici` CVEs will remain regardless -- see `docs/security/threat-model.md`'s
own residual-risks section for those).

## Gap: `pymupdf`'s AGPL-3.0/commercial dual licence is unresolved

**Status: CLOSED (Phase 6 Correction 2 §5, 2026-11-12).** **First
seen:** Phase 6A §11 (2026-11-06).

**What was missing:** a real decision on `pymupdf` (`pyproject.toml`:
`"pymupdf>=2.0,<3"`, imported directly in
`ledgerlight/processing/pdf.py` for real PDF extraction, part of the
application's own served code). It is dual-licensed: GNU AGPL-3.0, or
Artifex's commercial licence. This project held neither an Artifex
commercial licence nor a plan to release its own source under AGPL.

**Decision and fix:** the user chose AGPL-3.0 (LICENCE_CHOICE,
Correction 2 brief). This whole project is now licensed
AGPL-3.0-or-later: the real, full official licence text is
`LICENSE` (root), `pyproject.toml` declares
`license = "AGPL-3.0-or-later"` (PEP 639), `frontend/package.json`
declares the same, and `README.md` carries a Licence section
explaining why. Licensing the entire combined work under AGPL-3.0
satisfies `pymupdf`'s own AGPL-3.0 branch directly -- including for a
networked SaaS deployment, which is exactly what previously made this
a blocker. No Artifex commercial licence was obtained, and `pymupdf`
was not replaced; neither was necessary once the whole project itself
is AGPL-3.0.

**Evidence:** `docs/compliance/data-sources.md` §2's `pymupdf` finding
and §3 commercial-use statement, both now marked RESOLVED with the
same reasoning.

## Gap: 363 real corpus pages now trip the "no genuinely scanned PDFs" tripwire test

**Status: open.** **First seen:** incidentally, while verifying §11's
own test run (2026-11-06) -- not caused by any §11 change, and not a
code bug.

**What's missing:** `tests/test_corpus_processing.py::test_real_corpus_has_no_genuinely_scanned_pdf_pages`
is marked `@pytest.mark.corpus` (excluded from the normal default-
suite `addopts`, so it hadn't actually run in a while) and its own
docstring already anticipates this exact outcome: *"If this ever
fails, it means a real scanned page finally showed up, which is
useful to know, not a bug."* Running it today (`uv run pytest -m "not
integration" ...`, which incidentally overrides the `corpus`-excluding
default) found 363 real pages across the grown corpus (almost
certainly from Phase 3's large SEBI/IBBI/CARE discovery runs, which
added 300+ new real documents after this test's "zero" baseline was
established) now genuinely need OCR. Confirmed this is not caused by
anything in Phase 6A §11: reproduces identically on the clean,
pre-§11 commit (`git stash` + re-run).

**What this blocks:** nothing by itself -- `tests/test_ocr_engine.py`
already proves the real OCR path works on a synthetic fixture; this
finding has not been checked against *that* path to confirm these 363
specific real pages extract correctly through it rather than silently
losing content.

**Closing this gap requires:** running these 363 real pages through
the actual OCR path and spot-checking extracted text quality, then
either updating this test's hardcoded "zero" expectation to the new,
verified real count (with a note on why, mirroring how
`scripts/update_regression_snapshots.py` already handles a
legitimately-changed real baseline elsewhere in this project) or
fixing a real extraction problem if the spot-check finds one. Not
investigated further this phase -- outside §11's own scope
(compliance/licensing), flagged rather than silently fixed or
silently left for someone to discover by accident again.

## Gap: a real, confirmed bug drops real filings from some FINALISED dossiers

**Status: CLOSED (Phase 6 Correction 1 §2, 2026-11-07).** **First
seen:** Phase 6B review pass, 2026-11-07 (user-authorized AI review of
the §7 review pack -- see `docs/phase-6/phase-6b-review-findings.md`
for the full writeup and caveats).

**Root cause, confirmed not guessed:** the five affected investigations
ran on 2026-11-01 just BEFORE that same day's own verifier fix
(`timeline_entry` added to the real `verify_claim` dispatch,
commits `379fa27`/`9189752`) landed. Under the then-current code,
every `timeline_entry` claim fell through to the generic "unsupported
claim" check and failed closed; the investigations were never re-run
after the fix. Current code already dispatches `timeline_entry`
correctly -- this was a stale-data bug, not a live defect.

**Fix:** re-ran all 13 real dossiers fresh under current code --
every one FINALISED with claimed filings matching an independent
`get_timeline()` count, including all 5 previously-broken cases
(13/11/11/16/7 filings, all now correctly shown). Added a new,
permanent regression guard
(`ledgerlight.agent.verifier.check_timeline_claim_count`): any claim
of a filing count is now independently re-derived via `get_timeline()`
at verify time and fails closed to REPAIR/NEEDS_REVIEW on any future
mismatch, rather than silently finalizing an undercount. Regression
tests cover the 5 real cases plus a synthetic GATHER-drops-a-result
case.

**Evidence:** `docs/phase-6/evidence/sec2-root-cause-and-fix.md`,
`docs/phase-6/evidence/sec2-rerun-all-13.json`.

## Gap: dossier template renders the model card's "Intended use" text as a broken nested heading

**Status: CLOSED (Phase 6 Correction 1 §3, 2026-11-07).** **First
seen:** Phase 6B review pass, 2026-11-07.

**Fix:** `export_dossier_markdown`'s renderer now renders any
multiline sentence (the model card excerpt carries its own embedded
`## Intended use` heading) as a real Markdown blockquote instead of a
bare list item -- the embedded heading now nests correctly inside the
quote instead of escaping into the document's own outer heading
hierarchy. A new heading-hierarchy structure test
(`tests/test_agent_export.py`) parses every one of the 8 real
sections' rendered Markdown and asserts no stray heading can escape
its section, for both the regression case and every section carrying
multiline content. Golden dossier snapshot updated and documented
(`docs/phase-6/evidence/sec04-regression-snapshots.md`).

**Evidence:** `docs/phase-6/evidence/sec5-negation-hardening.md`'s
sibling commit messages (`phase-6: Correction 1 Sec3`), full diff in
`ledgerlight/agent/export.py`.

## Gap: `days_since_last_downgrade` univariate PR-AUC flag at 1.0 -- leak or artefact, unresolved

**Status: CLOSED (Phase 6 Correction 2 §1, 2026-11-12).** **First
seen:** Phase 3 §7 leakage audit, disclosed but not investigated.

**Investigation, real evidence, not guessed:** confirmed the flag is
in-sample/non-walk-forward/non-null-masked (as implemented), then
traced every real positive row's own downgrade `known_at` against its
outcome event -- ruling out the most natural leak hypothesis
(circular self-reference) with a real traced example (a 2020-10-28
B-downgrade feeding a 2022-01-02 D-outcome for FRETAIL, 431 days
apart, a distinct rating action from the outcome itself). The real
explanation: all 19 real non-null rows for this feature come from a
single company (FRETAIL) -- an extreme null-pattern sparsity artefact
(single-company autocorrelation), not a cross-company generalizable
signal, and not a temporal leak. LightGBM's own 0.267 pooled PR-AUC
(far below 1.0) is consistent with this: a feature that is perfectly
separating within one company contributes little pooled across 5.

**Fix:** no code fix needed (not a leak) -- `docs/modelling/data-quality.md`
and `docs/modelling/model-card.md` (generated, via `scripts/model_card.py`)
both updated with the full real evidence trace, replacing the prior
"disclosed, not confirmed" wording with the confirmed explanation.

**Evidence:** `docs/phase-6/evidence/sec1-downgrade-flag-investigation.md`.

## Gap: review routing never fired on real high-severity findings

**Status: CLOSED (Phase 6 Correction 2 §2, 2026-11-12).** **First
seen:** this phase's own brief (only a seeded QC task existed despite
72 real REPAIR-removed claims and real default-grade (D) rating
findings in real dossiers).

**Root cause, confirmed not guessed:** two independent gaps. (1)
`claims_from_outcomes_context`'s real IBBI/SEBI event claims never
carried `severity` in their payload at all -- `get_outcomes_context`'s
own SQL never selected `events.severity`, even though the real
underlying rows are created with `severity="high"`. (2) A
default-grade ("D") CARE rating is a `metric` claim, not an `event`
claim, and the routing check only ever inspected `event`-typed
claims' own `severity` field, making every rating observation
structurally invisible regardless of its real value.

**Fix:** `OutcomeEvent` now carries `severity`, threaded into the
claim payload; a new `_is_high_severity` recognises both a high-
severity event claim and a default-grade metric claim; two new
reason codes (`repair_removed_high_severity`,
`repair_emptied_section`) cover REPAIR-removed high-severity claims
and sections REPAIR left completely empty. Real dry run before/after:
`high_severity_finding` 3 -> 16, dossiers receiving >= 1 task 7 -> 55
(of 239). Backfilled for real, append-only, idempotent
(`scripts/backfill_review_routing.py --apply`): 58 new review tasks
created; a second `--apply` run creates 0 (confirmed idempotent). 9
new tests.

**Evidence:** `docs/phase-6/evidence/sec2-review-routing-fix.md`,
`docs/agent/review-workflow.md`.

## Gap: dossier rendering shows "Unknown company" and raw UTC timestamps in prose

**Status: CLOSED (Phase 6 Correction 2 §3, 2026-11-12).** **First
seen:** this phase's own brief (50 real dossiers' latest versions
showed "Unknown company" in the Sources section).

**Root cause, confirmed not guessed:** the Sources-section title used
`Document.company_name_raw or 'Unknown company'` -- a Phase 1
ingestion-time field that is almost always NULL in this corpus, never
the real `filings` link the brief asked for. Separately, every prose
date (`"known as of 2019-06-04T00:00:00+00:00"`) embedded the raw UTC
ISO timestamp verbatim rather than a human-readable local date.

**Fix:** the company name is now resolved via the real `filings` link
(`Filing.company_id -> Company.display_name`), scoped to the
dossier's own `company_id`, falling back to `company_name_raw` then
the investigation's own `company_name` before ever reaching "Unknown
company". Prose dates now render as the real Asia/Kolkata calendar
date (`"4 June 2019 (IST)"`); every stored/exported timestamp stays
UTC. Fixed a real regression this surfaced in
`ledgerlight.agent.verifier.check_sentence_values_in_claims` (the new
date format broke its number-containment heuristic, flipping 5 real
investigations to NEEDS_REVIEW) without weakening the check. A fresh
real agent-eval run (60 investigations) confirms 0 leakage and 60/60
FINALISED.

**Evidence:** `docs/phase-6/evidence/sec3-dossier-rendering-fixes.md`.
