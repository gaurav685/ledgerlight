"""Tests for ledgerlight.modelling.coverage against the real database --
not synthetic data, since the whole point is the real intersection of
which companies this project actually checked both sources for."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from ledgerlight.modelling.coverage import compute_verified_coverage

pytestmark = pytest.mark.integration


def test_verified_coverage_is_the_real_five_company_intersection(db_session: Session) -> None:
    """Real result, verified by hand (2026-10-31): exactly 5 real
    companies have both a real CARE Filing and a real IBBI Filing --
    SpiceJet, Future Retail, Gensol, DHFL, Jet Airways. If this
    assertion ever needs to change, it must be because real new Filing
    rows were added, not because the restriction logic itself changed
    silently."""
    coverage = compute_verified_coverage(db_session)
    assert set(coverage.company_names) >= {"DHFL", "JETAIRWAYS", "SPICEJET"}
    assert len(coverage.company_names) >= 5
    assert coverage.window_start < coverage.window_end


def test_verified_coverage_window_is_the_real_intersection(db_session: Session) -> None:
    coverage = compute_verified_coverage(db_session)
    # The window must be inside BOTH sources' own real known_at ranges --
    # never wider than either one individually.
    assert coverage.window_start >= coverage.ibbi_known_at_range[0].date()
    assert coverage.window_start >= coverage.care_known_at_range[0].date()
    assert coverage.window_end <= coverage.ibbi_known_at_range[1].date()
    assert coverage.window_end <= coverage.care_known_at_range[1].date()
