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


def test_admission_language_matches_real_confirmed_admission_phrasing() -> None:
    """Real bug found 2026-10-31 while rebuilding outcomes after the
    full-universe IBBI crawl: 'ABB India Limited' (a real, large, listed,
    never-insolvent company) showed up as a spurious admission because
    the one real IBBI document discovered for it was a Section 12A
    WITHDRAWAL order, not an admission. These two phrasings are real,
    verified admission-confirming text pulled from this project's own
    fetched IBBI orders."""
    real_admission_texts = [
        "the NCLAT admitted the said Company Petition and directed "
        "commencement of moratorium period in terms of Section 14 of IBC",
        "the Corporate Debtor was admitted into CIRP by this Tribunal on "
        "13.06.2025, whereupon the statutory moratorium under Section 14 "
        "of the IBC came into effect",
    ]
    for text in real_admission_texts:
        assert _MODULE._ADMISSION_LANGUAGE_PATTERN.search(text) is not None, text


def test_admission_language_does_not_match_real_withdrawal_order() -> None:
    """The real ABB India withdrawal order text (Section 12A) must NOT
    match -- it is the exact real false-positive case this pattern
    exists to reject."""
    real_withdrawal_text = (
        "I.A No.524 of 2019 and C.P(IB)No.210/BB/2018 U/s 12A of the IBC, "
        "2016 R/w Rule 11 of the NCLT Rules, 2016... is filed by Konduru "
        "Prashant Raju, (Applicant/IRP)... seeking to dispose of "
        "C.P(IB)No.210/BB/2018, as withdrawn"
    )
    assert _MODULE._ADMISSION_LANGUAGE_PATTERN.search(real_withdrawal_text) is None


def test_admission_language_does_not_match_corporate_debtor_admitting_a_debt() -> None:
    """Real second false positive found 2026-10-31 (AEPL, ABINFRA): the
    first draft's loose, non-directional "admitted ... Petition" matched
    this real text -- the Corporate Debtor admitting a DEBT is owed, with
    "Petition" merely appearing nearby in the next sentence, not the
    tribunal admitting the petition into CIRP."""
    real_debt_admission_text = (
        "the Corporate Debtor in the same email assured that it will try "
        "to make payment by end of July, 2020 and thus admitted its "
        "liability to make the payment of the three outstanding invoices. "
        "11. The Petitioner, therefore, addressed a Letter of Demand"
    )
    assert _MODULE._ADMISSION_LANGUAGE_PATTERN.search(real_debt_admission_text) is None


def test_admission_language_matches_real_dhfl_phrasing() -> None:
    """DHFL's own real admission evidence, as actually extracted by this
    detector in the real 2026-10-31 rebuild -- the one genuine "Petition
    IS/WAS admitted" case that must keep matching after the fix above."""
    assert _MODULE._ADMISSION_LANGUAGE_PATTERN.search("the petition was admitted") is not None


def test_admission_language_does_not_match_a_mere_petition_filing() -> None:
    """A real petition FILING notice (an Operational Creditor's petition
    against a Corporate Debtor) must not count as a confirmed admission
    -- the petition could still be dismissed or withdrawn before any
    real admission ever happens."""
    real_filing_text = (
        "IN STYLE FASHION ... Operational Creditor V/s ADITYA BIRLA "
        "FASHION AND RETAIL LIMITED ... Corporate Debtor / Respondent"
    )
    assert _MODULE._ADMISSION_LANGUAGE_PATTERN.search(real_filing_text) is None


def test_admission_language_does_not_match_a_mere_hearing_sheet() -> None:
    """A routine attendance/hearing sheet with no substantive order
    text must not count as a confirmed admission."""
    real_hearing_sheet_text = (
        "ATTENDANCE CUM ORDER SHEET OF THE HEARING HELD ON 01.09.2025 "
        "THROUGH VIDEO CONFERENCE PRESENT: HON'BLE SHRI. SANJIV JAIN, "
        "MEMBER (JUDICIAL)"
    )
    assert _MODULE._ADMISSION_LANGUAGE_PATTERN.search(real_hearing_sheet_text) is None
