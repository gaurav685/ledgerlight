# Phase 6 Correction 1 §2 — root cause and fix: "0 real filings known as of"

## Root cause (confirmed, not hypothesised)

Five real, already-FINALISED dossiers (DMART x2, VAKRANGEE, PNBHOUSING x2)
rendered "0 real filings known as of" while `get_timeline()` independently
returned real filings for the same `(company_id, as_of)`.

Two hypotheses were tested directly against the real persisted data and
**disproved**:

1. Timezone/precision mismatch in `check_timeline_entry_claim`'s `known_at`
   comparison — disproved by replaying the exact comparison with the real
   `document_versions.known_at` row and the real claimed `known_at`: `equal?
   True`.
2. The per-claim `check_timeline_entry_claim`/`verify_claim` logic itself
   being broken — disproved by calling both functions directly against the
   real persisted `Claim` row right now: both return `passed=True`.

The real cause, confirmed via `Claim.verification_checks` (persisted at the
time the original verification ran) and the real `InvestigationStep`
checkpoint history:

```
f581ce3b-... claim_type: timeline_entry verification_status: failed
  checks: [{'check_name': 'citation_resolves', 'passed': False,
            'detail': 'unsupported claim: timeline_entry claim has no evidence span'}]
```

This check name/detail only comes from `verify_claim`'s generic
"unsupported claim" branch (`ledgerlight/agent/verifier.py`), which fires
for any claim type NOT in `EVIDENCE_EXEMPT_CLAIM_TYPES` and not dispatched
to a dedicated check. Current code dispatches `timeline_entry` to
`check_timeline_entry_claim` *before* that branch can ever run — but these
five investigations' own `InvestigationStep` rows show their real PLAN
step completed between 06:33:54 and 06:46:03 UTC on 2026-11-01, and the
real git history shows the fix landing the same day:

```
379fa270c9d6 2026-11-01 12:17:52 +0530 (06:47:52 UTC) -- phase-4: Sec5 verifier
    EVIDENCE_EXEMPT_CLAIM_TYPES = {"risk_signal", "limitation"}
  + EVIDENCE_EXEMPT_CLAIM_TYPES = {"risk_signal", "limitation", "timeline_entry"}
9189752 3e7e1b 2026-11-01 14:02:12 +0530 (08:32:12 UTC) -- phase-5: Sec1 preflight
    adds the real dedicated check_timeline_entry_claim dispatch
```

**These five investigations ran under the pre-fix verifier**, before
`timeline_entry` claims were correctly handled, so all of their real
`timeline_entry` claims failed closed (correctly, under that day's
then-current code) and were excluded from the rendered dossier by
`_active_claims()`. The investigations were never re-run after the fix
landed, so the stale `FINALISED` dossiers persisted with 0 filings shown.
This is a **stale-data** bug, not a currently-live verifier defect — the
current verifier already handles `timeline_entry` claims correctly (see
`tests/test_agent_verifier.py::test_verify_claim_passes_a_timeline_entry_with_a_real_resolving_version`
and its siblings, pre-existing before this correction).

## Fix

1. Re-ran all 13 real dossiers (not just the 5 affected) fresh under
   current code via `run_investigation` (new `investigation_id` each,
   matching this project's append-only investigation model). Evidence:
   `docs/phase-6/evidence/sec2-rerun-all-13.json` — every one of the 13
   FINALISED with `claimed_filings == independent_filings`, including all
   5 previously-broken cases:

   | Company | as_of | claimed | independent | match |
   |---|---|---|---|---|
   | DMART | 2023-01-01 | 13 | 13 | yes |
   | DMART | 2019-01-01 | 11 | 11 | yes |
   | VAKRANGEE | 2023-01-01 | 11 | 11 | yes |
   | PNBHOUSING | 2023-01-01 | 16 | 16 | yes |
   | PNBHOUSING | 2019-01-01 | 7 | 7 | yes |

2. Added a new, independent verifier safeguard so this class of bug can
   never again silently reach FINALISE (§2.4's own requirement —
   "any claim of zero, none or a count must be recomputed by an
   independent query at verification time, and must match; a mismatch
   fails closed to REPAIR or NEEDS_REVIEW"):
   - `ledgerlight/agent/verifier.py::check_timeline_claim_count` —
     independently re-queries `get_timeline()` for the claims' own
     `(company_id, as_of)` and compares the real filing count against the
     number of `timeline_entry` claims passing verification THIS round.
   - Wired into `DossierVerificationResult.count_mismatches` and folded
     into `.passed`, so a mismatch fails the whole dossier closed.
   - Surfaced in the real `InvestigationStep` VERIFY checkpoint
     (`count_mismatches`) and in the NEEDS_REVIEW `failure_reason` string.

## Regression tests

- `tests/test_agent_verifier.py`:
  - `test_check_timeline_claim_count_matches_when_every_real_filing_has_a_claim`
  - `test_check_timeline_claim_count_catches_a_gather_dropped_filing` — the
    brief's own "synthetic case where GATHER drops results" requirement:
    a real third filing exists (real `filings`/`document_versions` rows)
    but no claim was ever made for it.
  - `test_verify_dossier_fails_closed_when_a_real_filing_claim_is_dropped` —
    same scenario wired through the full `verify_dossier` path.
- `tests/test_agent_state_machine.py::test_rerunning_a_previously_broken_real_dossier_shows_real_filings`
  — parametrized over the 5 real previously-broken `(company_id, as_of)`
  pairs; re-runs each fresh and asserts the dossier's claimed filing count
  equals the real, independently-queried count (never zero), with its own
  scoped cleanup (`_cleanup_one_investigation`) that never touches the
  real company or its other, pre-existing historical investigations.

All new/modified tests pass:
`test_agent_verifier.py -m integration -k "timeline_claim_count or dropped"`
→ 3 passed. `test_agent_state_machine.py -m integration -k
previously_broken` → 5 passed.
