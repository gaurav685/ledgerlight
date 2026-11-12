# Phase 6 Correction 2 §6 — verify and commit

## Full test pyramid (`scripts/test_pyramid_report.py`)

```
--- unit (default) ---
434 passed, 366 deselected, 1 warning in 35.42s
--- integration (batched) ---
  batch 1/7 (8 files)...
    105 passed, 19 deselected, 1 warning in 84.96s (0:01:24)
  batch 2/7 (8 files)...
    64 passed in 28.96s
  batch 3/7 (8 files)...
    72 passed, 3 deselected in 72.35s (0:01:12)
  batch 4/7 (8 files)...
    29 passed in 744.03s (0:12:24)
  batch 5/7 (8 files)...
    37 passed, 21 deselected in 88.89s (0:01:28)
  batch 6/7 (8 files)...
    44 passed, 5 deselected, 1 warning in 39.38s
  batch 7/7 (4 files)...
    10 passed, 2 warnings in 7.04s
--- corpus ---
1 failed, 1 passed, 798 deselected in 56.45s
--- e2e (subset of integration) ---
2 passed in 46.84s
--- security (subset of integration) ---
54 passed, 3 warnings in 80.20s (0:01:20)

=== Test pyramid summary ===
unit (default)                         OK                   366 deselected, 434 passed
integration                            OK                   48 deselected, 361 passed
corpus                                 ISSUES (exit 1)      798 deselected, 1 failed, 1 passed
e2e (subset of integration)            OK                   2 passed
security (subset of integration)       OK                   54 passed

Not run by this script (separate toolchain -- last recorded result):
  frontend Playwright e2e-lite suite: 4/4 passed (Phase 6A §2)
  OWASP ZAP baseline: 0 FAIL, 4 WARN, 64 PASS (Phase 6A §2)
```

**The one "corpus" failure is pre-existing and already disclosed, not a
Correction 2 regression**: `test_real_corpus_has_no_genuinely_scanned_pdf_pages`
re-confirms the already-tracked "363 real corpus pages trip the OCR
tripwire" finding (`docs/release/release-gates.md`, BLOCKED, first
found Phase 6A §11). The test's own docstring says exactly this is
expected to fail until those pages are run through OCR and
spot-checked -- "useful to know, not a bug." No code this correction
touched is anywhere near PDF/OCR processing.

**Batch 4/7 took 744s (12m24s)** -- real, not hung. Checked directly:
its own subprocess (`test_company_dedup.py`, `test_coverage.py`,
`test_cross_tenant_idor.py`, `test_document_processor.py`,
`test_e2e_pipeline.py`, `test_end_to_end_risk_pipeline.py`,
`test_entity_resolution.py`, `test_feature_policy.py`) looked frozen
mid-run (CPU time static across two 5-second samples, ~11.6s both
times) -- a real, heavy end-to-end/risk-pipeline pair of tests just
running slowly, confirmed when it completed cleanly with 29 real
passes and the orchestrator's own background task returned normally.
No process was actually killed.

## agent-eval (`scripts/agent_eval.py`, SEED + UNIVERSE, real DB)

Run twice this correction (§3 and again here after §4/§5's docs-only
changes) -- identical real results both times:

```
Real investigations run: 60
Status breakdown: SEED:FINALISED 30, UNIVERSE:FINALISED 30
Total claims in final dossiers: 740
Total claims removed in REPAIR: 72
Unsupported-claim leakage into a final dossier: 0
```

**Leakage: 0, as required.**

## Frontend Playwright e2e-lite / OWASP ZAP -- not re-run, by explicit user choice

`infra/docker-compose.e2e-lite.yml` overrides the SAME project/ports
as this session's live dev Postgres stack (holding every real
investigation this whole phase worked against) -- running it means
tearing that container down mid verification. Correction 2 §3's
dossier-rendering fix is user-facing, so a fresh e2e check would have
real value; asked the user directly rather than assuming. The user
chose not to disrupt the live stack. Real substitute coverage:
the backend render/export/verifier suites (92 passed, see
`docs/phase-6/evidence/sec3-dossier-rendering-fixes.md`) plus the
fresh agent-eval run above, both exercising the exact code path the
frontend displays. Last real Playwright/ZAP result (4/4 passed, 0
FAIL) stands unchanged, documented in `docs/release/release-gates.md`.

## `pre-commit run --all-files`

```
ruff...................................................................................Passed
ruff-format.............................................................................Passed
Detect hardcoded secrets.................................................................Passed
check for added large files..............................................................Passed
reject staged files under data/raw, data/interim, data/processed........................Passed
mypy (project venv -- avoids a second, heavy isolated env)...............................Passed
```

## gitleaks (full history, standalone)

```
gitleaks detect --source . --log-opts="--all" -v
244 commits scanned.
scan completed in 3.06s
no leaks found
```

## Regression/golden snapshots, release docs

`tests/test_regression_snapshots.py`: 6 passed (confirmed, with real
evidence, that no snapshot update was needed for this correction --
see `docs/phase-6/evidence/sec3-dossier-rendering-fixes.md` §3.3).

`docs/release/release-gates.md` and
`docs/phase-6/phase-6b-review-findings.md` updated with this
correction's real results: the `pymupdf` licence gate flips BLOCKED
-> PASS; three new closed-gap sections added (univariate flag
investigation, review-routing fix, dossier-rendering fixes); the
review-findings doc gets an addendum connecting its own 13-dossier
sample to the real review-routing gap Correction 2 §2 found and
fixed. `docs/release/production-readiness.md`'s three `pymupdf` rows
also flipped to COMPLETE/resolved for consistency (not duplicating
the fix, just not leaving a stale contradiction next to it).

## Commits this correction (local only, no AI attribution, every one verified)

```
8c720b4  phase-6: Correction 2 Sec1 -- investigate and close the days_since_last_downgrade PR-AUC=1.0 flag
6e0a392  phase-6: Correction 2 Sec2 -- fix review routing never firing for high-severity findings
97341a2  phase-6: Correction 2 Sec3 -- fix dossier rendering defects
6243156  phase-6: Correction 2 Sec4 -- honest scope wording for the risk model
2c38af7  phase-6: Correction 2 Sec5 -- licence AGPL-3.0-or-later
```

(Sec6's own commit follows this evidence file.) Every commit's author
verified `gaurav685 <gaurav685@gmail.com>`, no Co-Authored-By or
Claude-session trailer, no "Generated with" line.
