# Temporal Semantics — the `known_at` rule

Every `document_versions` row carries four distinct timestamps, all UTC
`timestamptz`. They answer four different questions, and conflating them
is exactly the kind of mistake that produces look-ahead bias in a
point-in-time system:

| Column | Question it answers |
|---|---|
| `retrieved_at` | When did **our** acquisition tool actually download this? |
| `published_at` | What publication date did **the source itself** state, if any? |
| `snapshot_at` | If this came from an archive (e.g. Internet Archive), when was that snapshot taken? |
| `known_at` | When could this information have **plausibly been known** by someone outside the source, for point-in-time analysis purposes? |

`known_at` is the one that matters for every later phase that needs to
avoid look-ahead bias (e.g. "what did the market know on date X").

## The rule

```
known_at = earliest TRUSTWORTHY evidence of public availability:
  1. the source's stated publication timestamp, IF that source is on the
     reliable list
  2. else the archive snapshot_at
  3. else retrieved_at
```

Implemented as one pure function:
`ledgerlight.db.temporal.compute_known_at()`, tested in
`tests/test_temporal.py`.

## Why a reliable-source allowlist, not "always trust published_at"

Not every "date" a source states is actually a publication date.
Concretely, in the Phase 0/Correction-1 corpus:

- **SEBI orders, IBBI NCLT orders, CARE rating rationales**: the stated
  date genuinely is the document's publication/issue date. These are on
  `RELIABLE_PUBLISHED_AT_SOURCES`.
- **NSE bhavcopy (`nse_archives`)**: `published_at` is the trading date
  the file covers. NSE publishes each day's bhavcopy that same evening,
  so treating the trade date as a reliable lower bound on `known_at` is
  safe — the data cannot have been known *before* the trading day it
  describes.
- **Company IR site documents** (shareholding patterns, annual reports):
  the stated date is almost always a **reporting period end**
  ("shareholding pattern as of 31 March 2022"), not the date it was
  actually published to the website. Treating that as `known_at` would
  claim knowledge earlier than the evidence supports — exactly what the
  rule forbids. These sources are deliberately **not** on the allowlist,
  so their `known_at` falls back to `retrieved_at` (our own download
  time), which is always a safe (if conservative) upper bound.

Phase 0's acquisition tool did not capture precise intraday publication
times for anything — `published_at` values used here are dates, not
instants; `known_at` for a reliable source is therefore the start of that
UTC day unless a more precise instant is available in future phases.

## IST → UTC conversion

Every source in this corpus is India-based and publishes in IST
(UTC+5:30). Where a source states a date with no explicit timezone (true
for all current sources), Ledgerlight interprets it as **IST midnight**
and converts explicitly to UTC before storing — i.e. a stated date of
`2019-06-05` becomes `2019-06-04T18:30:00Z`. This conversion happens once,
at ingestion time, never at query time, and is implemented alongside
`compute_known_at` rather than left to each ingestion module to get right
independently.

## Never infer an earlier known_at than the evidence supports

This is the one invariant every ingestion path must preserve. Concretely:
if a document's `published_at` is `None` (not stated, or from a
non-reliable source) and there is no `snapshot_at`, `known_at` **must**
fall back to `retrieved_at` — never to some other guessed-at date. The
function has no code path that can produce a `known_at` earlier than the
earliest value actually passed to it from a reliable source.
