"""Groups price_bars ISIN/symbol segments into real companies by union-find
over (isin, symbol) co-occurrence -- not by ISIN alone.

Real bug this fixes (found 2026-10-30 investigating a Phase 3 Sec2.4
auto-link gap): the original `scripts/bootstrap_companies.py` created one
`Company` row per distinct ISIN. That's correct for a company with a
single listed equity ISIN, but wrong for any company that has also issued
listed debt (NCDs/bonds): each bond tranche gets its own ISIN but trades
under the SAME `symbol` string as the company's equity in this corpus's
`price_bars` (confirmed by inspection, not assumed). DHFL alone fragmented
into 29 separate "companies" this way; 404 of ~4,929 real companies in the
whole universe were affected -- overwhelmingly NBFCs/bond issuers, exactly
the sector this project's risk modelling cares about most. See
`docs/phase-3/phase-3-report.md` Sec2.4 addendum for the full writeup and
`scripts/migrate_company_dedup.py` for the one-time data migration this
module's corrected logic drives.

Fix: two ISINs belong to the same real company if they have ever shared
the exact same `symbol` string in `price_bars` at any point in their
trading history -- true for every bond/equity pair issued by one company
observed in this corpus -- or if they are literally the same ISIN whose
symbol changed over time (a rename, already handled by the per-ISIN
segment ordering `scripts/bootstrap_companies.py` always had). Both
relations are folded into one union-find over ISINs.

Deliberate, disclosed simplification: this does not attempt to detect
genuine *symbol recycling* (two unrelated real companies using the exact
same symbol string in different eras) -- a materially harder problem
needing gap-based heuristics, and already an implicit assumption of the
pre-existing per-ISIN rename-tracking logic this module extends, not a
new risk this change introduces.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass


@dataclass
class IsinSegment:
    isin: str
    symbol: str
    seg_start: dt.date
    first_price_bar_id: uuid.UUID


@dataclass
class CompanyGroup:
    isins: list[str]
    segments: list[IsinSegment]  # every segment across every ISIN in this group

    @property
    def symbol_windows(self) -> list[tuple[str, dt.date, uuid.UUID]]:
        """Deduplicated (symbol, earliest seg_start for that symbol,
        source_price_bar_id) triples, sorted chronologically -- the basis
        for this group's NSE_SYMBOL identifier windows. In the common
        case (one symbol string shared by every ISIN in the group,
        concurrently) this collapses to a single triple, exactly right;
        a genuine rename (two distinct symbol strings used in sequence)
        still produces two triples, in order."""
        earliest: dict[str, tuple[dt.date, uuid.UUID]] = {}
        for seg in self.segments:
            current = earliest.get(seg.symbol)
            if current is None or seg.seg_start < current[0]:
                earliest[seg.symbol] = (seg.seg_start, seg.first_price_bar_id)
        return sorted(
            ((symbol, start, pb_id) for symbol, (start, pb_id) in earliest.items()),
            key=lambda triple: triple[1],
        )

    @property
    def latest_symbol(self) -> str:
        return max(self.segments, key=lambda seg: seg.seg_start).symbol

    @property
    def isin_earliest(self) -> dict[str, tuple[dt.date, uuid.UUID]]:
        """Per-ISIN earliest (seg_start, first_price_bar_id) -- what each
        ISIN's own CompanyIdentifier row should carry."""
        result: dict[str, tuple[dt.date, uuid.UUID]] = {}
        for seg in self.segments:
            current = result.get(seg.isin)
            if current is None or seg.seg_start < current[0]:
                result[seg.isin] = (seg.seg_start, seg.first_price_bar_id)
        return result


class _UnionFind:
    def __init__(self) -> None:
        self._parent: dict[str, str] = {}

    def find(self, x: str) -> str:
        self._parent.setdefault(x, x)
        path: list[str] = []
        while self._parent[x] != x:
            path.append(x)
            x = self._parent[x]
        for node in path:
            self._parent[node] = x
        return x

    def union(self, a: str, b: str) -> None:
        root_a, root_b = self.find(a), self.find(b)
        if root_a != root_b:
            self._parent[root_a] = root_b


def group_segments_into_companies(
    segments_by_isin: dict[str, list[IsinSegment]],
) -> list[CompanyGroup]:
    """The real grouping fix: union ISINs that ever shared a symbol
    string, not just treat each ISIN as its own company. Returns one
    CompanyGroup per real company as evidenced by this corpus, each
    possibly covering more than one ISIN."""
    uf = _UnionFind()
    symbol_to_isin: dict[str, str] = {}
    for isin, segs in segments_by_isin.items():
        uf.find(isin)
        for seg in segs:
            if seg.symbol in symbol_to_isin:
                uf.union(isin, symbol_to_isin[seg.symbol])
            else:
                symbol_to_isin[seg.symbol] = isin

    groups: dict[str, list[str]] = {}
    for isin in segments_by_isin:
        groups.setdefault(uf.find(isin), []).append(isin)

    return [
        CompanyGroup(
            isins=isins,
            segments=[seg for isin in isins for seg in segments_by_isin[isin]],
        )
        for isins in groups.values()
    ]
