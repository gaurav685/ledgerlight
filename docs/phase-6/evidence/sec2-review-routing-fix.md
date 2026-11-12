# Phase 6 Correction 2 §2 — review routing never fired

## §2.1 — the routing rules, exactly as implemented (before)

`ledgerlight.agent.review.determine_routing`, called via `create_review_tasks`
at the end of every real investigation (`run_investigation`, both the
normal and budget-exceeded paths):

| Code | Fired when | Priority |
|---|---|---|
| `high_severity_finding` | an **event** claim (`claim_type == "event"`) has `payload["severity"] == "high"` | high |
| `conflicting_evidence` | `dossier.sections["conflicting_evidence"]` non-empty | high |
| `verification_failed` | `final_status == "NEEDS_REVIEW"`, no budget mention | high |
| `budget_exceeded` | `final_status == "NEEDS_REVIEW"`, budget mentioned | high |
| `candidate_tier_majority` | > half of event claims are CANDIDATE tier | default |
| `low_confidence_extraction` | an event claim's own extracted field has `confidence < 0.7` | default |

Only called with `_active_claims(...)` -- the real claims REPAIR
removed were never passed in at all, so no rule could ever see them.

## §2.2 — real dry run, all 239 current dossiers, BEFORE the fix

```
high_severity_finding: 3
budget_exceeded: 2
candidate_tier_majority: 2
```
7 decisions total, across a handful of dossiers -- despite 690 real
failed (REPAIR-removed) claims and 19 active "D"-rating metric claims
existing right now in real, FINALISED dossiers.

## §2.1b/§2.3 — root cause, confirmed not guessed

Two independent, confirmed gaps:

1. **`claims_from_outcomes_context`'s IBBI/SEBI event claims never
   carried `severity` at all.** `get_outcomes_context`'s own SQL
   (`ledgerlight/agent/tools.py`) selected `e.id, e.event_time,
   e.known_at, e.status` -- never `e.severity` -- even though the
   real `Event` rows for `IBBI_CIRP_ADMISSION` and
   `SEBI_ORDER_AGAINST_COMPANY` are created with `severity="high"`
   (`scripts/populate_outcomes.py`). Confirmed directly against a real
   company (DHFL): before the fix, no severity was even available to
   check; after, every real IBBI/SEBI event claim correctly carries
   `severity="high"`.
2. **A default-grade ("D") rating is a `metric` claim, not an `event`
   claim**, and metric claims have no `severity` field at all --
   `event_claims = [c for c in claims if c.claim_type == "event"]`
   structurally excluded every CARE rating observation, regardless of
   its real value.

## §2.3 — the fix

- `ledgerlight/agent/tools.py`: `OutcomeEvent` gains a real `severity`
  field, selected directly from `events.severity`.
- `ledgerlight/agent/claims.py`: the event-claim payload now includes
  `"severity": event.severity`.
- `ledgerlight/agent/review.py`: new `_is_high_severity(claim)` --
  `severity == "high"` for an event claim, OR `name == "care_rating"
  and value in DEFAULT_GRADE_RATING_SYMBOLS ({"D"})` for a metric
  claim. `HIGH_SEVERITY_FINDING` now uses this for all claims, not
  just a bare event-claim severity check.
- `determine_routing` gains an optional `failed_claims` parameter (the
  real REPAIR-removed set) and two new reason codes:
  - `repair_removed_high_severity`: a failed claim that would itself
    have been high-severity.
  - `repair_emptied_section`: REPAIR removed every claim of the real
    claim type(s) that a now-empty section (`chronology`, `findings`,
    `risk_signals`) is built from -- one task per dossier, not one per
    section.
- `ledgerlight/agent/state_machine.py`: the one real call site now
  queries and passes both the active and the failed claim set (new
  `_failed_claims` helper, mirroring `_active_claims`).

Documented in full in `docs/agent/review-workflow.md`.

## §2.4 — real dry run AFTER the fix, then run for real

```
repair_emptied_section: 37
high_severity_finding: 16
repair_removed_high_severity: 3
budget_exceeded: 2
candidate_tier_majority: 2
```
60 decisions across 55 of 239 real dossiers (up from 7 across a
handful).

Ran for real, append-only, via the new
`scripts/backfill_review_routing.py --apply` (idempotent: skips any
(dossier, reason_code) pair that already has an open task):

```
--- 58 new review_tasks created ---
```
(60 real decisions minus the 2 pre-existing `budget_exceeded`/
`candidate_tier_majority` tasks already on file.) A second `--apply`
run creates 0 new tasks, confirming idempotency.

## §2.5 — tests

`tests/test_agent_review.py` (9 new tests): default-grade rating
flags high severity; a non-default rating does not; a real
IBBI/SEBI-shaped event claim with the now-populated `severity` field
flags high severity; a failed high-severity claim flags
`repair_removed_high_severity`; a failed low-severity claim does not;
an emptied `findings` section with a matching failed claim flags
`repair_emptied_section`; a non-empty section does not; an empty
section with an *unrelated* failed claim type does not (precision
check); multiple emptied sections still produce exactly one task.

`tests/test_agent_claims.py`: `claims_from_outcomes_context`'s own
event-claim payload now asserted to carry `severity == "high"`.

All green: `test_agent_review.py` (23), `test_agent_claims.py` (8),
`test_agent_state_machine.py` + `test_agent_adversarial.py` +
`test_api_review.py` (30, confirming the real call-site change causes
no regression).
