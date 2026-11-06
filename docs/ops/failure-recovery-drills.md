# Failure-Recovery Drills (Phase 6A §8)

Five real drills against the real local stack, each with real
before/after evidence (raw logs under `docs/phase-6/evidence/
sec08-drill*.log`). Two real, previously-undiscovered bugs were found
and fixed along the way (drill 4) -- disclosed below, not hidden.

## Drill 1: kill the worker mid-ingestion, resume with no duplicates

Started a real 6-document ingestion+processing batch as a subprocess,
`SIGKILL`ed it mid-batch, then re-ran the identical command to simulate
a restarted worker.

**Before (killed mid-batch)**: 1 of 6 documents logged as
"processed+chunked" before the kill signal landed. Real DB check right
after the kill showed 4 of 6 already had real pages/chunks -- more
than the log showed, because killing the parent process does not
necessarily kill the `multiprocessing.Process` child it spawns per
document for `run_with_timeout`'s own page-extraction timeout
(`ledgerlight/processing/document_processor.py`); an orphaned child
kept running (and logging) independently for a while after the parent
died. **Real, disclosed operational finding, not fixed here**: a true
production worker crash could leave an orphaned per-document
subprocess still writing to the database after the orchestrator
considers the job dead. Noted for whoever hardens worker supervision
next; out of this phase's own scope to re-architect.

**After (resumed, same command re-run)**: all 6 documents completed.
Final check: exactly 6 real `documents` rows, each with exactly 1
`document_versions` row, 1 page, and a non-zero chunk count -- **no
duplicates**, confirming the real idempotent-resume property.

Raw log: `docs/phase-6/evidence/sec08-drill1-worker-kill.log`.

## Drill 2: restart Postgres during real API traffic

```
curl .../v1/companies/{id}          -> 200 (baseline)
docker stop ledgerlight-phase0-postgres-1
curl .../v1/companies/{id}          -> 500, clean JSON error body, no hang
docker start ledgerlight-phase0-postgres-1
(wait for the container's own healthcheck)
curl .../v1/companies/{id}          -> 200 (clean recovery, no manual
                                        intervention beyond the restart)
```

Raw log: `docs/phase-6/evidence/sec08-drill2-postgres-restart.log`.
The API's own connection pool recovered automatically once Postgres
was back -- no API process restart was needed.

## Drill 3: Garage unavailable -- retries, dead letter, reprocess

Using the real `ledgerlight.ingestion.retry.run_with_attempt_tracking`
(the same function every real ingestion job uses):

```
docker stop ledgerlight-phase0-garage-1
attempt 1: FAILED -- EndpointConnectionError (real connection refused)
attempt 2: FAILED -- EndpointConnectionError
attempt 3: FAILED -- EndpointConnectionError
dead_letter row written: attempts=3, resolved_at=None
docker start ledgerlight-phase0-garage-1
(wait for healthy)
reprocess (attempt 4): SUCCESS, 77427 bytes
dead_letter row after reprocess: resolved_at=<real timestamp>,
  resolution="succeeded on a later attempt (attempt_number=4)"
```

Raw log: `docs/phase-6/evidence/sec08-drill3-garage-outage.log`. Real,
clean retry/dead-letter/reprocess/resolve cycle, exactly as designed.

## Drill 4: crash the agent mid-run, resume from checkpoint

Simulated a crash via a deliberately tiny budget (`max_steps=2`) --
the real, supported way this codebase lets an investigation stop
partway and be resumed later (a literal `SIGKILL` of `run_investigation`
mid-call isn't externally interruptible in a way that lands at a
useful point, since a real investigation's own runtime is ~0.08-9s;
the budget mechanism exercises the identical persisted-checkpoint
code path `resume_investigation_id` reads).

**Before (forced early stop)**:
```
state (checkpoint): GATHER
final_status: NEEDS_REVIEW
failure_reason: budget_exceeded: steps 2 >= max_steps 2
```

**Found two real, previously-undiscovered bugs** while building this
drill, both in `ledgerlight/agent/state_machine.py`'s `run_investigation`:

1. **Resume always silently ignored any new `budget_config` the caller
   passed**, always re-deriving the real PERSISTED (now-exhausted)
   budget instead. A real operator resuming a budget-exhausted
   investigation with a larger budget -- exactly what
   `scripts/investigate.py --resume <id> --max-steps 50` is
   documented to do -- would have the new budget silently discarded
   and immediately hit the identical exhausted budget again, with no
   indication why.
2. **`final_status`/`failure_reason` were never cleared on resume.**
   The code that decides FINALISED vs. NEEDS_REVIEW is gated on
   `if investigation.final_status is None`, which is always already
   false on a resumed investigation (set by the PRIOR failed attempt)
   -- so even a resumed run that genuinely reached FINALISE this time
   would stay permanently mislabelled NEEDS_REVIEW with a stale
   failure_reason from the earlier, unrelated failure.

Both confirmed by direct reproduction before the fix (resume failed
again with the same stale budget), then fixed: an explicit
`budget_config` override now wins and is persisted; `final_status`/
`failure_reason` are reset to `None` at the start of a resume, so the
investigation is judged fresh on what actually happens this time.
Re-ran the full `test_agent_state_machine.py` + `test_agent_adversarial.py`
suites after the fix -- all 19 tests still pass (no regression).

**After (resumed with a real larger budget, fix applied)**:
```
state: FINALISE
final_status: FINALISED
failure_reason: None
same investigation_id: True
```

Raw log: `docs/phase-6/evidence/sec08-drill4-agent-crash-resume.log`;
regression check: `docs/phase-6/evidence/sec08-drill4-regression-check.log`.

## Drill 5: expired session and revoked API key mid-use

**Revoked API key** (created via the real `POST /v1/api-keys`,
revoked via the real `DELETE /v1/api-keys/{id}`):
```
GET /v1/companies/{id} with the real key  -> 200 (before)
DELETE /v1/api-keys/{id}                  -> 204
GET /v1/companies/{id}, same key          -> 401 "invalid or expired API key"
```

**Expired session** (the real session row's `expires_at` set to the
past directly, simulating time passing):
```
GET /v1/companies/{id} with the real session cookie -> 200 (before)
UPDATE sessions SET expires_at = now() - interval '1 hour' ...
GET /v1/companies/{id}, same cookie                 -> 401 "invalid or expired session"
```

Raw logs: `docs/phase-6/evidence/sec08-drill5-revoked-api-key.log`,
`sec08-drill5-expired-session.log`. Both clean 401s, no crashes, no
stale access.

## Summary

| drill | before | after | real finding |
|---|---|---|---|
| Worker kill mid-ingestion | 1/6 logged done (4/6 really done) | 6/6 done, 0 duplicates | orphaned subprocess can outlive a killed parent (disclosed, not fixed) |
| Postgres restart | 200 | 500 during outage -> 200 after | clean, automatic pool recovery |
| Garage unavailable | 200 | 3 failures -> dead letter -> reprocess -> resolved | real retry/dead-letter cycle works as designed |
| Agent crash mid-run | NEEDS_REVIEW (budget_exceeded) | FINALISED (after 2 real bug fixes) | 2 real bugs found+fixed: resume ignored new budget; final_status never reset |
| Expired session / revoked key | 200 / 200 | 401 / 401 | clean, no stale access either way |
