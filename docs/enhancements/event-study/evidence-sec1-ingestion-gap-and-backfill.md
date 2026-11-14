# Real finding: sparse 2020-2025 price_bars ingestion, and the real
# limit on fixing it live

Found while reviewing the §1.2 detector's own first real run (8,688
detected factors -- implausibly high). Documented here because the
root cause and the resulting decision affect the honesty of the whole
§1 data-quality report, not just one number.

## The real sparse-density gap

`price_bars`'s own global distinct-`trade_date` count was 1,411 across
2016-01-01..2026-10-30 -- far short of the ~2,650 real NSE trading
days that range should have. Per year:

| year | distinct days (before) |
|------|------------------------|
| 2016 | 246 |
| 2017 | 248 |
| 2018 | 246 |
| 2019 | 244 |
| 2020 | 45 |
| 2021 | 23 |
| 2022 | 23 |
| 2023 | 24 |
| 2024 | 21 |
| 2025 | 87 |
| 2026 | 204 |

2020-2024 (and part of 2025) were real, pre-existing, already
documented (`docs/ingestion/runbook.md`: "Phase 0/Correction 1's seed
only sampled bhavcopy twice a month") -- the Phase 1 daily backfill
was run for 2019 (the runbook's own worked example) and apparently
2016-2018 and 2026, but never for 2020-2025.

## The real detector bug this caused

The §1.2 detector's own `_consecutive_session_pairs` checked adjacency
in the GLOBAL `price_bars` trading-day index, assuming that index is
itself a real, ~daily calendar. For 2020-2024 that index is itself
only ~2 dates/month, so two snapshot dates ~15 real calendar days
apart were wrongly treated as "one session apart" -- real ordinary
15-day price drift got misread as a single-day corporate-action-sized
jump. 5,763 of the first run's 8,688 "detections" (66%) were in
2020-2024. Fixed in `ledgerlight/modelling/price_adjustment.py` by
adding a real calendar-day bound (`MAX_REAL_CALENDAR_GAP_DAYS = 5`) on
top of index adjacency -- see
`tests/test_price_adjustment.py::test_detect_factors_for_isin_ignores_a_sparse_global_index_gap`.

## The real attempt to fix the data itself, and its real limit

Ran `scripts/backfill.py 2020-01-01 2025-12-31` (the project's own
documented tool for exactly this gap) to fetch the real missing daily
bhavcopy files live from `archives.nseindia.com`.

Real result: `business_days_attempted: 1566, fetched_new: 0,
unchanged: 790, not_found: 38, errors: 738`. Every single attempt to
fetch a genuinely new date from **2023-03-06 onward** failed:

```
2023-03-07: ConnectError: ('A required certificate is not within its
validity period when verifying against the current system clock or
the timestamp in the signed file.',)
```

This is a real, structural limit of this environment's live network
path to that one external historical-archive URL pattern -- not a bug
in this project's own code, and not something this session can fix
(it would require either changing the system clock or bypassing TLS
certificate validation, both explicitly out of bounds for an agent
to do unilaterally). The project's own **current-day** ingestion
schedule fetches 2026 dates successfully (`price_bars` already has
204 real days of 2026), so this is specific to the historical-archive
path for dates on or after 2023-03-06, not a general network outage.

## The real, better path that was actually available

A real, separate check found 996 real NSE bhavcopy documents already
sitting in object storage for 2020-2025 (fetched by some earlier,
unrecorded real session) -- far more than the ~223 dates actually
loaded into `price_bars`. Running `scripts/process.py` (the project's
own existing, idempotent, local-only loader -- no network calls) over
the full real backlog raised real daily density to:

| year | distinct days (after) |
|------|------------------------|
| 2020 | 249 |
| 2021 | 248 |
| 2022 | 248 |
| 2023 | 142 (capped -- no documents exist past 2023-03-05) |
| 2024 | 21 (unchanged -- no documents exist beyond the original seed) |
| 2025 | 87 (unchanged -- no documents exist beyond the original seed) |

`price_rows_upserted: 1,705,885` over the full real run (which also
processed the rest of the real document backlog: `price_files_processed:
2,195`, `errors: 310` -- 302 of those are `NoSuchKey` storage lookups
for unrelated non-price document versions, 8 are PDF OCR timeouts;
neither category touches `price_bars` and both are out of this
section's scope -- flagged for §3's own coverage review instead).

## Real, honest residual gap

2024 and most of 2025 remain at the original sparse twice-monthly
density -- genuinely missing real daily data, not fixable without
either live-fetching the blocked historical-archive range or a
different real data source. The calendar-gap fix above means this
sparse remainder now correctly yields near-zero detections for those
years (honest "we lack the resolution to tell", never a wrong
detection) rather than the first run's spurious high counts. This is
disclosed, not hidden, in the §1.3 data-quality report.
