# Production-readiness checklist (Phase 6A §14)

Every real capability this project has built or attempted, across all
six phases, marked **COMPLETE**, **PARTIAL**, or **BLOCKED** against
the project's own cumulative scope (no separate "master requirements"
document exists in this repo; this checklist reconstructs that scope
from every phase report, `README.md`, and `docs/release/release-gates.md`
-- the real, cited evidence, not a restatement of intent). No capability
below claims more than its own evidence supports.

**Legend**: COMPLETE = built, tested, verified, no known gap.
PARTIAL = built and real, with a specific, disclosed, real limitation.
BLOCKED = not usable for its intended purpose yet, with a specific,
disclosed reason.

## Data acquisition and sourcing

| Capability | Status | Evidence | Reason |
|---|---|---|---|
| Multi-source document acquisition (SEBI, IBBI, CARE, 10 company IR sites, NSE bhavcopy) | **COMPLETE** | `docs/data/source-inventory.md`, `data/manifests/sources.yaml`; real documents fetched and hash-verified across Phases 0/1/3 | -- |
| **BSE/NSE main sites** | **BLOCKED** | `docs/compliance/data-sources.md` | Edge bot-mitigation (Akamai) rejects this tool's honest, identifying User-Agent on every path tested, including `robots.txt` itself. Ground rules forbid spoofing a browser identity. NSE's bhavcopy archive is reachable via a separate subdomain (`nse_archives`, unaffected). |
| CRISIL, ICRA, MCA | **BLOCKED** | `docs/compliance/data-sources.md` | CRISIL/ICRA: robots.txt names AI-crawler user agents / a fingerprinting challenge. MCA: unconditional Access Denied regardless of User-Agent. |
| Thermax IR | **BLOCKED** (downgraded 2026-11-06) | `docs/compliance/data-sources.md` §11 | robots.txt now explicitly disallows `ClaudeBot` by name -- same precedent already applied to CRISIL, applied here for consistency. |
| Manual-download fallback path | **COMPLETE** | `ledgerlight/acquisition/import_local.py`, `docs/data/manual-download-checklist.md` | -- |
| Data-source compliance re-check (robots.txt/terms, dated) | **COMPLETE** | `docs/compliance/data-sources.md` (Phase 6A §11, 2026-11-06) | -- |

## Document processing

| Capability | Status | Evidence | Reason |
|---|---|---|---|
| PDF/HTML/bhavcopy/XBRL extraction | **COMPLETE** | `ledgerlight/processing/`, `docs/phase-1/phase-1-report.md` | -- |
| OCR fallback | **PARTIAL** | `tests/test_ocr_engine.py` (synthetic, passes); `docs/release/release-gates.md`'s "363 real corpus pages" gap | 363 real corpus pages (mostly from Phase 3's large discovery runs) now genuinely trip the OCR heuristic -- not yet run through the real OCR path and spot-checked for extraction quality. |
| Subprocess isolation / timeout safety | **COMPLETE** | `ledgerlight/processing/runner.py`, `ledgerlight/processing/limits.py` | -- |
| **`pymupdf` licensing** | **BLOCKED for commercial use** | `docs/compliance/data-sources.md`, `docs/release/release-gates.md` | Dual-licensed AGPL-3.0/Artifex commercial; this project holds neither. Does not block research/internal use. |

## Knowledge extraction, entity resolution, retrieval

| Capability | Status | Evidence | Reason |
|---|---|---|---|
| Event classification | **PARTIAL** (GOLD on `test` split only) | `docs/evaluation/final-evaluation.md`: rules macro-F1 0.635 [0.432, 1.000], n=14 gold | Several silver-label error rates are real and high (`ID_EXIT` 83.3%, `RPT_GROWTH` 66.7%); `RATING_ACT`/`FORENSIC` have zero gold coverage reachable from `test`/`validation`. |
| Structured extraction (AUD_RESIGN) | **PARTIAL** (SILVER-UNREVIEWED) | `docs/evaluation/final-evaluation.md`: 6/6 real fields validated | Gold human review is `PENDING_HUMAN_REVIEW` -- Phase 6B's job. |
| Entity resolution | **PARTIAL** (SILVER-UNREVIEWED) | `docs/evaluation/final-evaluation.md`: 3/3 correct, too thin for pairwise P/R/F1 | Same gold-review gap; corpus too small for a real precision/recall claim. |
| Hybrid retrieval (BM25 + embedding + RRF) | **PARTIAL** (SILVER-UNREVIEWED) | `docs/evaluation/final-evaluation.md`: recall@10 0.667, MRR 0.330 | Query-relevance judgements are `ai_constructed_unreviewed`, not human-reviewed. |
| GUIDANCE_MISS extraction | **BLOCKED -- no data** | `docs/modelling/guidance-extraction-assessment.md` | Searched all 4,759 real corpus pages; 0 real management-issued guidance statements exist anywhere in the corpus. No extraction machinery was built against data that doesn't exist. |

## Temporal risk model

| Capability | Status | Evidence | Reason |
|---|---|---|---|
| Point-in-time feature pipeline | **COMPLETE** | `docs/modelling/`, Phase 3 §4: 100% of feature rows satisfy `max_input_known_at <= as_of`, 0 violations | -- |
| **Predictive validity** | **BLOCKED -- inconclusive** | `docs/modelling/model-card.md` (generated): PR-AUC 0.267 [0.099, 0.649], Brier skill score -0.221 (worse than base rate) | Real, verified-coverage universe is only 5 companies / 5 pooled distinct positive events -- below the brief's own 30-event floor for any predictive-skill claim. No model variant (B0-B3, LightGBM) beats the training-fold base rate. **Not investment advice; must not be used for any real decision.** |
| **Financial features** | **BLOCKED -- excluded** | `docs/phase-3/phase-3-report.md` §5 | Excluded with real evidence (too much real missingness in the available universe) rather than shipped untested. |
| Leakage/survivorship/ablation audits | **COMPLETE** | `scripts/leakage_check.py`, `scripts/ablation.py`, Phase 3 report | Real, disclosed anomalies noted (shifted-PR-AUC artifact, one univariate flag at 1.0) -- neither confirmed as a leak given the sample size. |
| Backtest reproducibility | **COMPLETE** | Phase 6A §5, `docs/phase-6/progress.md` | One real sub-step (`build_feature_snapshots.py`) marked BLOCKED by host memory, not code -- independently confirmed row-count-identical against the live DB instead. |

## Investigation agent and dossiers

| Capability | Status | Evidence | Reason |
|---|---|---|---|
| State machine, tools, offline template renderer | **COMPLETE** | `docs/phase-4/phase-4-report.md`, `docs/architecture.md` | No live LLM call anywhere, by design -- Phase 4's own ground rule, not a missing API key. |
| Per-claim verifier | **COMPLETE** | `docs/evaluation/final-evaluation.md`: 0 unsupported-claim leakage across 740 claims; 14/14 adversarial tests passed. Freshly re-confirmed, Phase 6 Correction 1 §6 (2026-11-07): 60/60 real investigations FINALISED, 0 NEEDS_REVIEW, 0 unsupported-claim leakage. | -- |
| Human review of real dossiers | **BLOCKED -- not yet done** | `docs/release/release-gates.md` "no human review...has ever happened" | Explicitly deferred to Phase 6B by the brief's own instruction. The review pack itself (5 tools, deterministic sampling, audit trail) is built and ready. The Phase 6B review that DID run was by an AI under explicit user override -- real QA, never gold, quarantined (Correction 1 §1) -- this gate stays genuinely open. |
| Resume-with-new-budget / stale-status bugs | **COMPLETE (fixed)** | Phase 6A §8, `ledgerlight/agent/state_machine.py` | Two real, previously-undiscovered bugs found and fixed this phase. |
| "0 real filings" dossier-rendering bug | **COMPLETE (fixed)** | Phase 6 Correction 1 §2, `docs/phase-6/evidence/sec2-root-cause-and-fix.md` | Real, found by the AI-performed Phase 6B review; root-caused, fixed, re-validated across all 13 real dossiers; new permanent independent-count regression guard added. |
| "Intended use" markdown-bleed renderer bug | **COMPLETE (fixed)** | Phase 6 Correction 1 §3, `ledgerlight/agent/export.py` | Same provenance; fixed via a proper Markdown blockquote, with a new heading-hierarchy structure test. |
| 3 field-citation mismatches (THERMAX/RELCAPITAL/BCG) | **PARTIAL (2 of 3 fixed)** | Phase 6 Correction 1 §4, `docs/phase-6/evidence/sec4-field-citation-fixes.md` | THERMAX (detector-level) and BCG (new document-identity check) fixed; RELCAPITAL is a genuine name-collision no automated check can resolve, stays flagged PENDING_HUMAN_REVIEW. |
| Negated resignation language in silver labels/detector | **COMPLETE (fixed)** | Phase 6 Correction 1 §5, `docs/phase-6/evidence/sec5-negation-hardening.md` | Both the silver proposer and the real AUD_RESIGN detector now require non-negated resign/cease language; developed only against dev/gold-validation, never the frozen test split. |

## Human review infrastructure (gold-label status)

| Capability | Status | Evidence | Reason |
|---|---|---|---|
| Field/entity-pair/retrieval-query review tooling | **COMPLETE (built)** | `scripts/field_review.py`, `entity_pair_review.py`, `retrieval_review.py`, `outcome_evidence_review.py`, `docs/phase-6/human-review-guide.md` | -- |
| **Actual gold review** | **BLOCKED -- PENDING_HUMAN_REVIEW** | `docs/evaluation/final-evaluation.md` | No human has reviewed anything through these tools yet -- explicitly Phase 6B's job, not this phase's. Every SILVER-UNREVIEWED tier above depends on this. |
| 10-dossier + outcome-evidence human spot-checks | **BLOCKED -- built, not run** | `docs/release/release-gates.md` | Same reason; sample built, review pending a human. |

## API, security, tenancy

| Capability | Status | Evidence | Reason |
|---|---|---|---|
| RLS tenancy, auth/sessions/CSRF/API keys | **COMPLETE** | `docs/security/threat-model.md`, `docs/adr/0008-api-auth-tenancy.md` | -- |
| Full `/v1` surface | **COMPLETE** | `docs/api/openapi.json` (regenerated 2026-11-06, confirmed current), `docs/api/usage-guide.md` | -- |
| Security test suite (authz, IDOR, CSRF, SSRF, rate limits, prompt-injection) | **COMPLETE** | `docs/phase-6/evidence/sec09-security-suite.log`: 97 passed, 0 failures | -- |
| Dependency vulnerabilities (`pip-audit`) | **COMPLETE** | Phase 6A §9: 24 real vulnerabilities found and fixed, 0 remaining | -- |
| Frontend CSP | **PARTIAL** | `docs/security/threat-model.md` residual risks | `script-src 'unsafe-inline'` with no working nonce -- a real Next.js 16.4.3 hydration-script limitation found this phase; mitigated by no `dangerouslySetInnerHTML` anywhere and no raw document HTML ever rendered as markup. |
| Deployed Docker images' dependency freshness | **BLOCKED** | `docs/release/release-gates.md` | Images predate the §9 dependency fix; rebuild attempted twice, killed twice by real host memory pressure. The fix exists in `pyproject.toml`/`uv.lock`; only the baked image is stale. |

## Frontend, orchestration, ops

| Capability | Status | Evidence | Reason |
|---|---|---|---|
| Next.js analyst frontend | **COMPLETE** | `docs/frontend/architecture.md`; confirmed starting and serving `/login` from a truly fresh clone (Phase 6A §13) | -- |
| Dagster orchestration | **COMPLETE** | `ledgerlight/orchestration/definitions.py` | -- |
| Load test, throughput measurement, failure-recovery drills | **COMPLETE** | `docs/ops/performance-and-reliability.md`, `docs/ops/failure-recovery-drills.md` | Small-scale by design (5 concurrent users) -- a real measurement, not a production capacity claim. |
| Backup/restore | **COMPLETE** | `docs/ops/restore.md`, real drill verified | -- |
| Ops runbooks | **COMPLETE** | `docs/ops/` (10 real runbooks) | -- |
| Per-filing cost measurement + AWS cost model | **COMPLETE** | `docs/ops/cost-per-filing.md` | -- |

## Testing and QA

| Capability | Status | Evidence | Reason |
|---|---|---|---|
| Default test suite | **COMPLETE** | 408/408 passed, confirmed fresh from a clean clone (Phase 6A §13) | -- |
| Integration suite | **COMPLETE** | 330/330 passed, in memory-safe batches (Phase 6A §1, §9) | Requires batching on this host due to real, recurring memory pressure -- disclosed, not hidden. |
| Golden-fixture regression suite | **COMPLETE** | `tests/test_regression_snapshots.py`, Phase 6A §4 | -- |
| Real end-to-end pipeline test | **COMPLETE** | Phase 6A §3 | -- |
| Playwright e2e + OWASP ZAP baseline | **BLOCKED -- not run this phase** | `docs/release/release-gates.md` | Deferred due to real host memory constraints. |
| A single-batch full integration run | **BLOCKED -- not captured** | `docs/release/release-gates.md` | Same real memory constraint; the batched-run result is equally valid evidence, just not a single-pass one. |

## Documentation

| Capability | Status | Evidence | Reason |
|---|---|---|---|
| Architecture doc, data dictionary | **COMPLETE** | `docs/architecture.md`, `docs/data-dictionary.md` (both new, Phase 6A §12/§13) | Data dictionary reflects the live DB schema directly (52 real tables) after a real gap (a raw-SQL-only table with no ORM model) was found and fixed. |
| API docs | **COMPLETE** | `docs/api/openapi.json` (regenerated 2026-11-06 -- found and fixed real drift from the §9 dependency bump) | -- |
| Model card | **COMPLETE** | `docs/modelling/model-card.md` -- regenerated this phase, confirmed byte-identical (genuinely current) | -- |
| README | **COMPLETE** | Rewritten Phase 6A §12, verified against a real clean-install run §13 | -- |
| Deployment docs | **COMPLETE** | `docs/deploy/aws-architecture.md`, `docs/deploy/local-setup-windows.md` -- both reconciled/fixed this phase | -- |

## CI/CD and deployment

| Capability | Status | Evidence | Reason |
|---|---|---|---|
| **GitHub Actions workflows** | **BLOCKED -- UNVERIFIED** | `docs/release/release-gates.md`, 5 workflows validated locally only | No remote configured (GIT POLICY: local-only, no push, this phase and every prior one). Cannot be verified until a first real push happens. |
| **AWS deployment** | **BLOCKED -- not deployed** | `docs/deploy/aws-architecture.md` | Terraform is validated (`terraform fmt`/`validate`) but never applied -- no AWS credentials in this environment, and applying infrastructure is explicitly out of scope. |
| Local Docker Compose stack | **COMPLETE** | `infra/docker-compose.yml`, confirmed working via the real, currently-running dev stack and independently via Phase 6A §13's clean-install test | Real constraint found this phase: the Compose project name and host ports are hardcoded, so a second instance cannot safely run alongside the first on one machine -- a real, disclosed limitation, not a blocker for normal single-instance use. |

## Legal and licensing status

| Capability | Status | Evidence | Reason |
|---|---|---|---|
| Python dependency licences (195 packages) | **COMPLETE, 1 flagged** | `docs/phase-6/evidence/sec11-python-licences.md` | All permissive except `pymupdf` (see below). |
| npm dependency licences (332 packages) | **COMPLETE** | `docs/phase-6/evidence/sec11-npm-licences-summary.log` | All permissive. |
| Model checkpoint licences | **COMPLETE** | `docs/compliance/data-sources.md` §2 | Both real models (`BAAI/bge-small-en-v1.5`, `MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli`) are MIT, explicitly commercial-use-permitted. |
| Container base image licences | **COMPLETE** | `docs/compliance/data-sources.md` §2 | Python/Node/pgvector all permissive. Garage is AGPL-3.0 but used unmodified as a separate networked service -- low risk, not a blocker. |
| **`pymupdf` dual licence** | **BLOCKED -- unresolved** | `docs/compliance/data-sources.md`, `docs/release/release-gates.md` | AGPL-3.0 or Artifex commercial; this project holds neither. Blocks any commercial/SaaS launch of the real PDF-extraction functionality until resolved (Artifex licence, or a library swap). Does not block research/internal use today. |
| Data redistribution policy | **COMPLETE** | `docs/adr/0002-data-acquisition-policy.md` | Raw documents never committed; only manifests (metadata) are, since most sources require permission before redistributing content. |

## Git and backup policy

| Capability | Status | Evidence | Reason |
|---|---|---|---|
| Local-only commits, no AI attribution | **COMPLETE** | Every commit this phase verified via `git log --format='%H%n%an <%ae>%n%B'` | -- |
| Backup bundles | **PARTIAL** | `../ledgerlight-backups/ledgerlight-phase-{1..5}.bundle` exist | Phase 6A's own bundle is created in §17 (not yet reached). |
| Push to a remote | **BLOCKED -- by policy** | GIT POLICY, every phase | No remote configured; explicitly reserved, not this project's current policy to push. |

## Overall summary

Of the capabilities above: the data pipeline, document processing,
agent, API, frontend, security hardening, ops tooling, and
documentation are all real and **COMPLETE**. The three capabilities
that most constrain any real-world use of this platform today are, in
order of severity:

1. **The risk model makes no predictive-skill claim** (statistically
   inconclusive on 5 real events) -- this platform's "red flag"
   scoring is not validated for any real decision.
2. **No gold human review has happened yet** -- every extraction/
   entity-resolution/retrieval/dossier metric above GOLD-tier
   classification is silver-unreviewed, pending Phase 6B.
3. **`pymupdf`'s AGPL-3.0 licensing question is unresolved** -- blocks
   commercial/SaaS use specifically, not research/internal use.

Everything else (BSE/NSE/CRISIL/ICRA/MCA/Thermax blocks, AWS not
deployed, GitHub Actions unverified, financial features excluded,
guidance extraction blocked for lack of data) is a scoped, disclosed,
non-blocking limitation of this specific research prototype, not a
defect hiding behind a passing test suite.
