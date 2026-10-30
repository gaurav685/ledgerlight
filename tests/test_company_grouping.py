"""Tests for ledgerlight.ingestion.company_grouping -- the Phase 3 Sec2.4
fix for the real company-fragmentation bug (one Company row per ISIN
instead of per real company). Each case mirrors a real pattern found in
this corpus's price_bars (see the module docstring and
docs/phase-3/phase-3-report.md's Sec2.4 addendum)."""

from __future__ import annotations

import datetime as dt
import uuid

from ledgerlight.ingestion.company_grouping import (
    IsinSegment,
    group_segments_into_companies,
)

PB = uuid.uuid4


def test_simple_equity_only_company_is_its_own_group() -> None:
    """The common case (~4,525 of ~4,929 companies): one equity ISIN,
    never renamed. Must stay a single, unaffected group."""
    segments = {
        "INE_CLEAN_EQ": [IsinSegment("INE_CLEAN_EQ", "CLEAN", dt.date(2017, 1, 5), PB())],
    }
    groups = group_segments_into_companies(segments)
    assert len(groups) == 1
    assert groups[0].isins == ["INE_CLEAN_EQ"]
    assert groups[0].latest_symbol == "CLEAN"


def test_dhfl_like_bond_fragmentation_is_merged_into_one_company() -> None:
    """Real pattern: one equity ISIN plus many bond ISINs, ALL sharing
    the exact same symbol string concurrently. Must merge into ONE group
    -- this is the real bug this module fixes."""
    segments = {
        "EQ_ISIN": [IsinSegment("EQ_ISIN", "DHFL", dt.date(2016, 1, 1), PB())],
        "BOND_ISIN_1": [IsinSegment("BOND_ISIN_1", "DHFL", dt.date(2016, 8, 19), PB())],
        "BOND_ISIN_2": [IsinSegment("BOND_ISIN_2", "DHFL", dt.date(2017, 4, 17), PB())],
        "BOND_ISIN_3": [IsinSegment("BOND_ISIN_3", "DHFL", dt.date(2018, 6, 6), PB())],
    }
    groups = group_segments_into_companies(segments)
    assert len(groups) == 1
    assert set(groups[0].isins) == {"EQ_ISIN", "BOND_ISIN_1", "BOND_ISIN_2", "BOND_ISIN_3"}
    assert groups[0].latest_symbol == "DHFL"
    # Exactly one symbol window: all four ISINs share the same symbol string,
    # so this must NOT fragment into multiple windows.
    windows = groups[0].symbol_windows
    assert len(windows) == 1
    assert windows[0][0] == "DHFL"
    assert windows[0][1] == dt.date(2016, 1, 1)


def test_genuine_rename_still_produces_two_symbol_windows() -> None:
    """Real pattern the ORIGINAL per-ISIN logic already handled
    correctly: one equity ISIN whose symbol changed once. Must still
    produce two chronologically-ordered windows, unaffected by the fix."""
    segments = {
        "SAME_ISIN": [
            IsinSegment("SAME_ISIN", "OLDNAME", dt.date(2015, 1, 1), PB()),
            IsinSegment("SAME_ISIN", "NEWNAME", dt.date(2019, 6, 1), PB()),
        ],
    }
    groups = group_segments_into_companies(segments)
    assert len(groups) == 1
    windows = groups[0].symbol_windows
    assert [w[0] for w in windows] == ["OLDNAME", "NEWNAME"]
    assert windows[0][1] == dt.date(2015, 1, 1)
    assert windows[1][1] == dt.date(2019, 6, 1)
    assert groups[0].latest_symbol == "NEWNAME"


def test_two_unrelated_companies_never_sharing_a_symbol_stay_separate() -> None:
    """No symbol ever shared between these ISINs -- must stay two
    distinct companies, not accidentally merged."""
    segments = {
        "ISIN_A": [IsinSegment("ISIN_A", "ALPHA", dt.date(2017, 1, 1), PB())],
        "ISIN_B": [IsinSegment("ISIN_B", "BETA", dt.date(2017, 1, 1), PB())],
    }
    groups = group_segments_into_companies(segments)
    assert len(groups) == 2
    assert {tuple(g.isins) for g in groups} == {("ISIN_A",), ("ISIN_B",)}


def test_transitive_merge_across_three_isins() -> None:
    """A real possible pattern: ISIN A and B share symbol X; B and C
    share symbol Y (e.g. B is a bond that also appears under a second
    recorded symbol value due to a data quirk). Union-find must merge
    all three transitively into one company."""
    segments = {
        "ISIN_A": [IsinSegment("ISIN_A", "SYM_X", dt.date(2017, 1, 1), PB())],
        "ISIN_B": [
            IsinSegment("ISIN_B", "SYM_X", dt.date(2017, 1, 1), PB()),
            IsinSegment("ISIN_B", "SYM_Y", dt.date(2018, 1, 1), PB()),
        ],
        "ISIN_C": [IsinSegment("ISIN_C", "SYM_Y", dt.date(2017, 1, 1), PB())],
    }
    groups = group_segments_into_companies(segments)
    assert len(groups) == 1
    assert set(groups[0].isins) == {"ISIN_A", "ISIN_B", "ISIN_C"}


def test_isin_earliest_picks_the_minimum_seg_start_per_isin() -> None:
    segments = {
        "ISIN_A": [
            IsinSegment("ISIN_A", "SYM", dt.date(2018, 1, 1), PB()),
            IsinSegment("ISIN_A", "SYM", dt.date(2016, 1, 1), PB()),
        ],
    }
    groups = group_segments_into_companies(segments)
    earliest = groups[0].isin_earliest
    assert earliest["ISIN_A"][0] == dt.date(2016, 1, 1)
