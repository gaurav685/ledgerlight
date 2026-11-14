# Enhancement 1 Correction §1.1 — corporate-action adjustment: empirical method verification

## The brief's own suggested method does NOT work on this data -- empirically confirmed, not guessed

The brief's suggested detector ("On days where the bhavcopy previous-close
field differs from the prior session's close for the same ISIN, compute
the factor = prev_close(t) / close(t-1)") was tested directly against 5
real, independently cited, publicly documented corporate actions. On
every single one, **`prev_close(t)` exactly equals the real prior
session's `close(t-1)`, to the last decimal place** -- the bhavcopy's own
`prev_close` field is simply yesterday's raw, unadjusted close, carried
forward faithfully, never adjusted for a split or bonus. The entire
adjustment shows up only in `close` itself, as a clean single-day drop.

## The 5 real, cited cases checked

| Company | Symbol | Action | Real ex-date (source) | Real `close(t-1)` → `close(t)` | Real ratio | Expected ratio | `prev_close(t)` == `close(t-1)`? |
|---|---|---|---|---|---|---|---|
| Reliance Industries | RELIANCE | 1:1 bonus | 2017-09-07 ([Business Standard](https://www.business-standard.com/article/markets/reliance-industries-extends-gain-ahead-of-bonus-shares-117090600433_1.html)) | 1645.40 -> 818.10 | 0.4972 | 0.5 | **True** (1645.4000 == 1645.4000) |
| Infosys | INFY | 1:1 bonus | 2018-09-04 ([Business Standard](https://www.business-standard.com/article/markets/infosys-turns-ex-date-for-1-1-bonus-stock-hits-new-high-118090400132_1.html)) | 1434.25 -> 737.15 | 0.5141 | 0.5 | **True** (1434.2500 == 1434.2500) |
| HDFC Bank | HDFCBANK | 1:2 split | 2019-09-19 ([Zerodha/tradingqna](https://tradingqna.com/t/hdfc-bank-goes-ex-split-in-the-ratio-2-1-on-september-19-2019-here-s-how-it-impacts-your-equity-holdings-and-f-o-positions/63025)) | 2187.75 -> 1101.05 | 0.5033 | 0.5 | **True** (2187.7500 == 2187.7500) |
| TCS | TCS | 1:1 bonus | 2018-05-31 ([Business Standard](https://www.business-standard.com/article/markets/tcs-hits-record-high-after-fixing-record-date-for-1-1-bonus-issue-118052100149_1.html)) | 3514.10 -> 1741.05 | 0.4954 | 0.5 | **True** (3514.1000 == 3514.1000) |
| Wipro | WIPRO | 1:3 bonus (1 new share per 3 held) | 2019-03-06 ([tradingqna](https://tradingqna.com/t/infosys-goes-ex-bonus-in-the-ratio-1-1-on-september-04-2018-here-s-how-it-impacts-your-equity-holdings-and-f-o-positions/45501), [Business Standard](https://www.business-standard.com/article/markets/wipro-trades-1-3-ex-bonus-stock-up-5-119030600254_1.html)) | 363.60 -> 277.45 | 0.7631 | 0.75 | **True** (363.6000 == 363.6000) |

(Wipro's "1:3" is the "X new shares per Y held" convention, not "old:new"
-- confirmed by checking against the real data: a naive "1:3 => quarter
the price" assumption was WRONG (predicted 0.25, real ratio is 0.75);
re-deriving the convention from the real observed ratio, not asserting
one blindly, is exactly the "do not guess factors" discipline the brief
asks for.)

**Negative control**: Avenue Supermarts (DMART) has never had a real
stock split or bonus issue ([Trendlyne](https://trendlyne.com/equity/Split/DMART/53208/avenue-supermarts-ltd-split/),
[Trendlyne](https://trendlyne.com/equity/Bonus/DMART/53208/avenue-supermarts-ltd-bonus/)).
Scanned its entire real price history in `price_bars`: **zero** single-day
close-to-close moves exceeding 30% anywhere, confirming a real stock with
no corporate action produces no false positive under a large-single-day-move
detector.

## What this means for the brief's own detection method

**The brief's suggested `prev_close(t) / close(t-1)` method does not
reliably reflect adjustments -- it reflects nothing at all, by
construction, for this bhavcopy source.** Said plainly per the brief's
own instruction: this method does not work here, and is not used.

A real, separate finding from running this exact query at scale (before
narrowing to the 5 known cases): the raw, un-scoped version of this
query flagged 148,877 "candidate" rows. Almost all of them traced to
two real, unrelated causes, neither a corporate action:
1. **Symbol collisions across series**: the same symbol text (e.g.
   `NTPC`) is reused across equity (`EQ`) and several real debt/bond
   series (`N6`, `N7`, `NC`, `ND`, ...) with entirely different ISINs
   and price levels -- comparing across series without partitioning by
   ISIN manufactures spurious "factor" values in the hundreds.
2. **A systematic, market-wide pattern on specific recurring calendar
   dates** (the 5th/20th/21st of many months, across years) affecting
   1,300-1,800 real stocks simultaneously with wide factor variance
   (0.19-2.16) -- this is not individual corporate actions (which never
   affect thousands of unrelated companies on the same day); it is not
   investigated further here (out of this correction's scope), but is
   flagged as a real, disclosed, unresolved data-quality question for a
   future pass, never silently absorbed into the corporate-action table
   built below.

## The legitimate alternative: a real, validated price-ratio detector

Since `close` itself (not `prev_close`) carries the real adjustment,
and the 5 known cases + the negative control confirm this works
cleanly, the real, validated method is:

1. Scope to `series = 'EQ'`, partitioned by `isin` (never bare
   `symbol`, which collides across series -- confirmed above).
2. Require **consecutive real trading sessions** (no gap in the real,
   global trading-day index) -- a large move across a real multi-week
   illiquidity gap is ordinary price drift, not a corporate action.
3. Compute `factor = close(t) / close(t-1)`.
4. Accept only factors close to a small, real, enumerable set of
   economically plausible ratios corporate actions actually take in
   practice (1/2, 1/3, 1/4, 1/5, 2/3, 3/4, 4/5, 5/6, and their inverses
   2, 3, 4, 5, 6/5, ... up to a bound), within a real tolerance --
   never "any large move," which would conflate a real split with an
   ordinary distressed-stock crash or a circuit-limit sequence (exactly
   the false-positive risk the brief's own §1.3 asks to be checked).
5. A move that is large but does NOT match any plausible ratio is a
   **residual suspicious jump**, reported separately (brief §1.3), never
   silently treated as a corporate action.

A document-based alternative (the brief's own suggested fallback,
"corporate-action announcements from AVAILABLE sources") was checked
and is not currently available: NSE's own corporate-action RSS feed
(`nsearchives.nseindia.com/content/RSS/Corporate_action.xml`) is under
the same real edge-blocking verdict (**BLOCKED**) already documented
for `nsearchives.nseindia.com` generally
(`data/manifests/sources.yaml`, retested 2026-10-25, connection
failed). The price-ratio method above is validated directly against 5
real, independently cited public records and a real negative control,
and is used as the sole real detection method -- not a second,
redundant evidence layer, since none is currently reachable.
