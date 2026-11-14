# Incident: real `price_bars` CLOG corruption, found and repaired during Enhancement 1 Correction §1

This affects the **core project database**, not just the event study
-- documented here because it was found while running the real
corporate-action detector, and the fix was completed before resuming
that work.

## What happened

Running `scripts/detect_price_adjustments.py` against the live DB hit
a real, reproducible Postgres error on a specific real ISIN:

```
psycopg.errors.UndefinedFile: could not access status of transaction 2806092208
DETAIL:  Could not open file "pg_xact/0A74": No such file or directory.
```

This means Postgres could not determine whether a specific real row's
inserting transaction had committed, because the commit-log (CLOG /
`pg_xact`) segment covering that transaction ID was missing from
disk -- real corruption, not a bug in this correction's own code.

## Scope, confirmed precisely (binary search, read-only)

- `price_bars` has 177,368 real pages. A page-range binary search
  (2000 pages -> 50 pages -> 1 page granularity) found the corruption
  confined to exactly **16 contiguous pages** (168576-168591) -- 176
  real tuples, **0.006% of the table's ~3.06M real rows**.
- The real rows immediately bounding the bad range share the same
  real `version_id` (`0091b1a0-4b7c-45af-b7d1-5ab8c2c8241f`),
  `source_id='nse_archives'`, and `trade_date='2026-07-27'` -- the
  corruption is confined to one single real bhavcopy ingestion
  transaction, specifically the alphabetical symbol slice between
  `MHRIL` (last good row before) and `MONIFTY500` (first good row
  after).
- Nothing else in the table was affected -- confirmed by a full
  89-batch page scan across the entire table, both before and after
  the repair.

**Likely cause**: this session had several real, independently
confirmed host low-memory kills earlier while running heavier
background work; an abrupt interruption mid-write/mid-checkpoint for
this one specific ingestion transaction is the most likely real
explanation, though this was not provable definitively.

## Repair, with explicit user authorization at each step

1. Confirmed a real, complete, intact backup exists as a fallback:
   `../ledgerlight-backups/db/ledgerlight-20261104T184350Z.dump`
   (full `pg_dump`, custom format, 2026-11-04, verified via
   `pg_restore --list` -- 356 real TOC entries including a real
   `price_bars` `TABLE DATA` entry).
2. Installed `pg_surgery` and `pageinspect` (both real, standard
   PostgreSQL contrib extensions, not yet installed in this
   database).
3. Used `pageinspect.heap_page_items()` to enumerate the real, exact
   tuple line pointers on the 16 bad pages (176 real tuples) --
   bypassing the broken MVCC visibility check entirely, since
   `pageinspect` reads raw page bytes.
4. Used `pg_surgery.heap_force_kill('price_bars', <176 real tids>)`
   to remove exactly those dead tuples -- the Postgres-blessed real
   recovery tool for this exact failure mode. Verified immediately
   after: the same page range now returns 0 rows with no error
   (previously it errored on every read).
5. Ran `scripts/reprocess.py 0091b1a0-4b7c-45af-b7d1-5ab8c2c8241f`
   (an existing project tool -- reads the already-stored real
   document from the object store, re-parses the real CSV, and
   upserts into `price_bars`, never re-fetching over the network).
   Real result: `rows_parsed: 3453, rows_upserted: 178,
   rows_unchanged: 3275, quarantined: 0`.
6. Spot-checked the real re-inserted rows (72 real rows for
   2026-07-27 between `MHRIL` and `MONIFTY500`) -- real, sensible
   prices and ISINs (e.g. `MIDHANI` close 397.10, `MIDWESTLTD` close
   1240.10).

## A real, separate incident during verification

While running the final full-table verification re-scan, the
Postgres container itself crashed (`docker inspect`: `ExitCode=255`,
**`OOMKilled=false`** -- not the host memory-pressure pattern seen
elsewhere this session). No FATAL/PANIC was logged before the gap;
the container's own logs simply stop at 16:02:04 UTC and the
container's `FinishedAt` is 16:15:18 UTC, with nothing logged in
between.

Restarted with `docker start` (a normal, non-destructive recovery
action for a stopped container). Real recovery log, in full:

```
2026-11-13 17:32:26.841 UTC [29] LOG:  database system was interrupted; last known up at 2026-11-13 15:58:21 UTC
2026-11-13 17:32:27.370 UTC [29] LOG:  database system was not properly shut down; automatic recovery in progress
2026-11-13 17:32:27.375 UTC [29] LOG:  redo starts at 3/BED67D10
2026-11-13 17:32:27.397 UTC [29] LOG:  invalid record length at 3/BEFB2550: expected at least 24, got 0
2026-11-13 17:32:27.397 UTC [29] LOG:  redo done at 3/BEFB2518 ...
2026-11-13 17:32:27.459 UTC [1] LOG:  database system is ready to accept connections
```

Standard, successful WAL crash recovery -- exactly the mechanism
Postgres provides for this. Verified afterward, all real:
- `SELECT count(*) FROM price_bars` -- 3,063,934 (matches the real,
  previously-recorded count from earlier phases of this project).
- The repaired range (2026-07-27, `MHRIL` < symbol < `MONIFTY500`) --
  still 72 real rows.
- The specific previously-bad 16-page ctid range -- 0 rows, no error.
- A full, fresh 89-batch page scan across the entire real table --
  **0 bad batches, 0% corruption**.

## Real, honest conclusion

The repair is complete, durable (survived a real crash+restart), and
fully verified. The corruption was real, narrow (0.006% of one
table), and now resolved. Enhancement 1 Correction work resumes from
here.
