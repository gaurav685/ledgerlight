"""Tests for scripts.ibbi_universe_discovery's CSV parsing -- the real
NSE equity master file format (note the leading spaces after commas in
the header, confirmed live 2026-10-30, not assumed)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
_SPEC = importlib.util.spec_from_file_location(
    "ibbi_universe_discovery", REPO_ROOT / "scripts" / "ibbi_universe_discovery.py"
)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules["ibbi_universe_discovery"] = _MODULE
_SPEC.loader.exec_module(_MODULE)

REAL_CSV_SAMPLE = (
    "SYMBOL,NAME OF COMPANY, SERIES, DATE OF LISTING, PAID UP VALUE,"
    " MARKET LOT, ISIN NUMBER, FACE VALUE\n"
    "20MICRONS,20 Microns Limited,EQ,06-OCT-2008,5,1,INE144J01027,5\n"
    "21STCENMGM,21st Century Management Services Limited,EQ,03-MAY-1995,10,1,INE253B01015,10\n"
)


def test_parse_master_csv_real_header_shape() -> None:
    companies = _MODULE._parse_master_csv(REAL_CSV_SAMPLE)
    assert len(companies) == 2
    name, identifiers = companies[0]
    assert name == "20 Microns Limited"
    assert identifiers.nse_symbol == "20MICRONS"
    assert identifiers.isin == "INE144J01027"


def test_parse_master_csv_skips_rows_missing_symbol_or_name() -> None:
    csv_text = "SYMBOL,NAME OF COMPANY, SERIES\n,Some Name,EQ\nSYM2,,EQ\nSYM3,Real Name,EQ\n"
    companies = _MODULE._parse_master_csv(csv_text)
    assert len(companies) == 1
    assert companies[0][0] == "Real Name"


def test_parse_master_csv_handles_a_real_short_row() -> None:
    """Real bug (2026-10-30 live run): csv.DictReader yields None, not
    '', for a short row's missing trailing fields -- crashed the first
    live attempt at scripts/ibbi_universe_discovery.py's parsing, which
    called .strip() unconditionally."""
    csv_text = (
        "SYMBOL,NAME OF COMPANY, SERIES, ISIN NUMBER\n"
        "SYM1,Real Name,EQ\n"  # one field short: ISIN NUMBER missing -> None
    )
    companies = _MODULE._parse_master_csv(csv_text)
    assert len(companies) == 1
    assert companies[0][0] == "Real Name"
    assert companies[0][1].isin is None
