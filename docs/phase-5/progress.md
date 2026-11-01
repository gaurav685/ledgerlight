# Phase 5 Progress

Read `docs/phase-5/brief.md` first (the complete, verbatim brief), then this file,
before resuming any session. Branch: `phase-5/api-ui-security`, to be created from
Phase 4's completion commit `d1daf12`.

## Sections done

(none yet -- brief just saved)

## Not yet started

- §1: preflight (branch, green baseline, verbatim Phase 3/4 evidence, verifier-fix
  audit, review-routing audit, stop-condition check).
- §2: tenancy, auth, RBAC (migrations, RLS, sessions, API keys, permission matrix).
- §3: the API (FastAPI /v1, all endpoints, rate limits, audit logs, alert generation).
- §4: the frontend (Next.js App Router, all pages, security headers, accessibility).
- §5: Docker Compose, config, secrets, seed command.
- §6: production deployment config (AWS architecture doc, Terraform -- not applied).
- §7: CI/CD workflows (validated locally only -- no GitHub remote).
- §8: observability, backup/restore, runbooks.
- §9: security tests (authz matrix, cross-tenant isolation, auth, signed URLs,
  webhooks, rate limiting, input validation, prompt-injection separation, security
  headers, Playwright e2e, optional ZAP baseline).
- §10: documentation (API docs, security docs, frontend/deploy/ops docs, 2 new ADRs,
  release-gates.md update, README update, phase-5-report.md).
- §11: run and verify.
- §12: final commit/backup.
- §13: exit gates.
- §14: final report, `docs/phase-5/phase-5-report.md`.

## Exact next step

§1 preflight: create branch `phase-5/api-ui-security` from `d1daf12`, run the full
checks for a green baseline, print the required verbatim Phase 3/4 sections, run the
verifier-fix audit and review-routing audit, check the 4 stop conditions. Do not
proceed into §2 if any stop condition triggers.

## Pending items carried over from the end of Phase 4 (not part of this brief, flagged
so they are not lost)

- User asked to push the Phase 4 backup bundle to a git remote -- no remote is
  configured (`git remote -v` empty); asked user for the remote URL, not yet answered.
  This brief's own GIT POLICY is "commit locally only, no remote, no push" -- same as
  every prior phase -- so this stays parked unless/until the user gives a URL and
  confirms the override explicitly.
- User asked to "check SpiceJet's control-group decision" -- the real, still-open
  human decision from Phase 3 report §17.1 (8 real NCLT petitions found against
  SpiceJet 2021-2026, calling its original "no known distress" Phase 0 role into
  question). Not yet resolved; options from that section:
  1. Keep SpiceJet with the current disclosed caveat.
  2. Reclassify it.
  3. Drop it from evaluation entirely (would not change the pooled positive-event
     count, since its events are already censored out, but would change the universe's
     company count and B1's rule-based predictions in several folds).
  This is a human decision, not something to resolve unilaterally; flagged here to
  surface again once Phase 5's own work reaches a natural pause point, or sooner if
  the user asks.

## Open defects / known limitations (carried forward from Phase 4, relevant to Phase 5)

- 69 of 127 real `event_fields` rows (`order_document`) have a genuinely zero-length
  evidence span -- correctly fails citation_resolves; relevant to Phase 5's event
  timeline/evidence-link UI (a real event may legitimately have no highlightable span).
- The Phase 3 risk model is statistically inconclusive; every Phase 5 score view must
  keep the model-limitations banner, per the brief's own §4 requirement.
- No EVENT-CANDIDATE event type meets the Phase 3 reliability bar; Phase 5's event
  timeline must keep showing VERIFIED/CANDIDATE tier badges.
- Human review of real dossiers has never happened (deferred to Phase 6,
  `docs/release/release-gates.md`) -- Phase 5's review-queue UI exists so this CAN
  happen, but doing the actual review is still out of scope here too.
- SpiceJet's control-group status (see above) -- unresolved, human decision pending.
