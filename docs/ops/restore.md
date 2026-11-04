# Backup / restore

Phase 5 §8. Real backup and a real, verified restore drill -- both
proven to work this phase (`docs/phase-5/evidence/restore-drill.log`),
not simulated.

## Backup

```powershell
uv run python scripts/backup.py
```

Does two things against the real running local stack:

1. `pg_dump -Fc` of the real `ledgerlight` database, via `docker exec`
   into the real `ledgerlight-phase0-postgres-1` container (never
   requires `pg_dump` installed on the host).
2. A real object-by-object sync of the real Garage bucket
   (`ledgerlight-raw`) -- every object downloaded, with its sha256
   checked against the hash its own content-addressed key name
   carries (`raw/<sha256[:2]>/<sha256><ext>`), before being written to
   disk.

Output goes to `../ledgerlight-backups/` (one level above the repo --
never committed, same convention this project already uses for its
git bundle backups):

```
../ledgerlight-backups/db/ledgerlight-<timestamp>.dump
../ledgerlight-backups/objects/<timestamp>/raw/...
```

Run this before anything destructive (a migration you're unsure
about, `docker compose down -v`, a bulk data fix) and on whatever
real schedule the deployment needs -- there is no cron/schedule wired
up for this yet; it is a manual script today.

## Restore drill

```powershell
uv run python scripts/restore_drill.py
```

Always operates on the MOST RECENT backup under
`../ledgerlight-backups/`. Does a REAL restore, not a dry run:

1. Creates a fresh, disposable database (`ledgerlight_restore_drill`)
   and runs `pg_restore` into it from the dump.
2. Compares real row counts for every one of the real database's
   tables (queried from `pg_tables`, not a hardcoded list) between the
   source database and the restored one, and prints the full
   side-by-side table.
3. Creates a fresh, disposable Garage bucket
   (`ledgerlight-raw-restore-drill`) and uploads every backed-up
   object into it, re-verifying each one's sha256 against its key
   after the round trip.
4. Drops the drill database and bucket again -- this proves the
   backup restores correctly, it does not leave a second live copy of
   real data behind.

Exit code is non-zero if any row count mismatches or any object fails
its post-restore hash check -- safe to wire into a scheduled check
once backups themselves are scheduled.

**Last real run** (`docs/phase-5/evidence/restore-drill.log`): all 53
tables matched exactly; all 2,626 objects restored and sha256-verified.

## Restoring for real (not a drill)

If an actual restore is ever needed (not a drill), the two building
blocks above show the real commands -- `pg_restore` into the real
`ledgerlight` database (after confirming with whoever is on call that
overwriting it is intended), and re-uploading the synced objects into
the real `ledgerlight-raw` bucket. There is no one-command "restore
for real" script on purpose: a destructive restore against the real
database should not be a single accidental invocation away from the
drill command.
