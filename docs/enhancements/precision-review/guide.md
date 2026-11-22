# Precision Review Guide — KMP_EXIT, ID_EXIT, RPT_GROWTH

This guide is for the real human reviewer running
`scripts/precision_review.py` against the fresh sample in
`data/manifests/precision-review-v1.jsonl`. For each item, decide
whether the detector-flagged type is correct, a different real event
type, not a real event at all, or skip with a note if genuinely unsure.

One rule per type below, with one `correct` example and one
`not-an-event` example each. Examples are short, synthetic excerpts
(no more than 15 words), not real filing text.

## KMP_EXIT

A CEO, Managing Director, CFO, Company Secretary or whole-time director
**resigned or ceased** to hold office. Appointments and routine board/KMP
rosters do not count — only a departure.

- **correct**: "The Company Secretary has resigned with effect from
  12 March 2025."
- **not-an-event**: "Board of Directors and KMP as on 31 March 2025:
  Name, Designation, DIN."

## ID_EXIT

An **independent director** resigned or ceased to hold office. A board
composition table listing independent directors, without a departure,
does not count.

- **correct**: "Mr. X, Independent Director, has ceased to be a
  director with effect from 1 April 2025."
- **not-an-event**: "The Board comprises five Independent Directors as
  per the composition table below."

## RPT_GROWTH

A **related-party transaction amount** compared across two or more
periods, showing growth. Policy text and a bare "disclosed in Note X"
cross-reference do not count — only quantified, multi-period amounts.

- **correct**: "RPT with ABC Ltd rose from ₹12 crore in FY23 to ₹18
  crore in FY24."
- **not-an-event**: "All related-party transactions are disclosed in
  Note 42 to these financial statements."

## Negation

Negation ("no resignation during the year", "nil related-party
transactions") is **always not-an-event**, for any of the three types
above, regardless of how closely the surrounding text otherwise matches
the rule.

## Decisions

- **correct**: a real disclosed event of exactly the flagged type,
  about the flagged company.
- **wrong-type**: a real event, but a different type than flagged.
- **not-an-event**: boilerplate, policy text, appointments, negation,
  or a passing mention — nothing actually happened.
- **skip**: genuinely unsure; add a note explaining why.

## Why no cited sub-span

Both production methods for these three types (`rules_baseline` for
KMP_EXIT/ID_EXIT, `tfidf_lr` for RPT_GROWTH) classify the **whole
chunk** — neither returns a specific span inside it the way the real
AUD_RESIGN field-extractor does. The tool shows the full chunk text
instead of a highlighted span; this is disclosed in the tool's own
output, not a gap this guide should paper over.
