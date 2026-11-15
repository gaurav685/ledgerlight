# Changelog

All notable changes to Ledgerlight are recorded here. Dates are the
real date the work was done, not a release-cut date.

## [v0.9.0-preview] — 2026-11-15

First push to a remote. Portfolio preview; human review gates not
completed; not for investment decisions. See
`docs/release/release-notes-v0.9.0-preview.md` for the full writeup.

### Phases 0-5

Data acquisition, document processing, knowledge extraction/entity
resolution, temporal risk modelling, the investigation agent, and the
API/UI/security layer were all built across six phases. See each
phase's own `docs/phase-N/phase-N-report.md` for detail.

### Phase 6: integrated validation and release

Cross-phase re-verification, security hardening (97 real security
tests, 24 dependency vulnerabilities found and fixed), licensing
resolution (`pymupdf`'s AGPL-3.0/Artifex dual licence resolved by
licensing this whole project AGPL-3.0-or-later), dossier-rendering and
review-routing bug fixes, and an honest restatement of the risk
model's real scope (5-company verified-coverage sample, no
demonstrated predictive skill).

### Enhancement 1: governance event study (not yet merged to main)

Pre-registered market-reaction event study (CAR, BMP, Corrado rank,
Holm-Bonferroni, placebo tests) on `enhancement/event-study`. First
real run: 56 primary events, no statistically significant result
after correction -- reported honestly as a null result.

### Enhancement 1 Correction, §1 (not yet merged to main)

Empirically-validated corporate-action (split/bonus) price-adjustment
pipeline on the same branch. Found and fixed a real database
corruption incident, a missing index, and a real sparse-ingestion
data-quality bug along the way -- all disclosed in
`docs/enhancements/event-study/evidence-sec1-*.md`. §2-§5 of the
Correction (feature rebuild, coverage-funnel review, spec v2) remain
not started.

### Known defects and gaps (not fixed this release)

- OCR fallback: 363 real corpus pages trip the tripwire, not yet
  spot-checked for extraction quality.
- Human gold review of extraction/entity-resolution/retrieval/dossier
  quality has not happened yet (Phase 6B's job, explicitly deferred).
- Frontend CSP still uses `script-src 'unsafe-inline'` -- a real
  Next.js 16.4.3 hydration-script limitation, mitigated by never using
  `dangerouslySetInnerHTML`.
- Deployed Docker images predate a dependency fix (the fix is in
  `pyproject.toml`/`uv.lock`; the baked image is stale).
- AWS deployment: Terraform validated, never applied (no AWS
  credentials in this environment).
