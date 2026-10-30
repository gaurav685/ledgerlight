"""Tests for scripts.populate_outcomes's pure regex/heuristic pieces --
the case-number extraction (for grouping IBBI orders by case, to find
the earliest-dated one as an admission proxy) and the CARE "rated D"
pattern (for the rating-downgrade-to-default primary outcome), both
checked against real phrasing seen in this project's own fetched
documents."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
_SPEC = importlib.util.spec_from_file_location(
    "populate_outcomes", REPO_ROOT / "scripts" / "populate_outcomes.py"
)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules["populate_outcomes"] = _MODULE
_SPEC.loader.exec_module(_MODULE)


def test_case_number_pattern_matches_real_ibbi_subject() -> None:
    text = (
        "In the matter of Jet Airways (India) Ltd. "
        "[IA No. 5729 of 2025 in CP (IB) No. 2205 of 2019]"
    )
    match = _MODULE._CASE_NUMBER_PATTERN.search(text)
    assert match is not None
    assert "2205" in match.group(0)


def test_case_number_pattern_matches_sebi_style_ib_case() -> None:
    text = "IA/3976/2026 in IB-674/ND/2024"
    match = _MODULE._CASE_NUMBER_PATTERN.search(text)
    assert match is not None


def test_rating_d_pattern_matches_real_care_phrasing() -> None:
    for text in (
        "CARE has downgraded the rating to CARE D",
        "the instrument is rated D",
        "the long-term rating has been downgraded to D",
    ):
        assert _MODULE._RATING_D_PATTERN.search(text) is not None, text


def test_rating_d_pattern_does_not_match_unrelated_text() -> None:
    assert _MODULE._RATING_D_PATTERN.search("CARE has reaffirmed the rating at AA") is None


def test_looks_like_etf_consistent_with_drawdown_script() -> None:
    assert _MODULE._looks_like_etf("GOLDSHARE")
    assert not _MODULE._looks_like_etf("INFY")


def test_normalize_case_number_unifies_real_dhfl_variants() -> None:
    """Real bug (2026-10-30 live run): DHFL's single real case (docket
    4258/2019) was extracted as four differently-formatted strings
    across its four real order documents, grouping into 4 spurious
    "admissions" instead of 1 under exact-string matching."""
    variants = [
        "CP (IB) No. 4258/",
        "CP(IB)No. 4258/",
        "CP (IB) No. 4258/2019",
    ]
    normalized = {_MODULE._normalize_case_number(v) for v in variants}
    assert normalized == {"4258"}


def test_normalize_case_number_falls_back_to_stripped_text_when_no_digits() -> None:
    assert _MODULE._normalize_case_number("no digits here") == "no digits here"
