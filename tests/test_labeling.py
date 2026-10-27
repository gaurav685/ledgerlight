"""Tests for the silver label proposer.

Real bug found while running this against the real corpus (v1): sampling
'none' examples by `enumerate()` position was non-idempotent, because
the chunks query had no ORDER BY, so a second run could return chunks in
a different order and sample a different subset as 'none' -- creating
duplicate-looking but distinct proposals every run. Fixed by sampling
deterministically from chunk.id instead of query-result position.

Phase 3 §1.4 hardening (v2) tests below use real text drawn from the
actual gold-reviewed dev-split/validation-split errors that motivated
each rule change (see labeling.py's module docstring and
docs/modelling/event-reliability.md) -- not synthetic examples invented
to make the rule look good.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.orm import Session

from ledgerlight.knowledge.labeling import propose_event_type, propose_labels
from ledgerlight.knowledge.models import Chunk

pytestmark = pytest.mark.integration


def test_propose_event_type_matches_real_aud_resign_pattern() -> None:
    # The exact real-world pattern that broke a stricter proximity regex
    # during v1 development: the subject and verb are separated by a
    # firm name across a line break. v2 additionally requires a date,
    # present here as it is in the real filing.
    text = (
        "UPDATE ON RESIGNATION FROM THE AUDIT ENGAGEMENT\n"
        "BY THE STATUTORY AUDITOR - PRICE WATERHOUSE & CO\n"
        "CHARTERED ACCOUNTANTS LLP (PWC)\n\n"
        "Mumbai, April 28, 2018: This is to hereby inform that Price Waterhouse & Co "
        "Chartered Accountants LLP (PWC) has resigned."
    )
    assert propose_event_type(text) == "AUD_RESIGN"


def test_propose_event_type_aud_resign_without_date_is_none() -> None:
    # Same text, no date anywhere -- v2's extra requirement over v1.
    text = (
        "BY THE STATUTORY AUDITOR - PRICE WATERHOUSE & CO\n"
        "This is to hereby inform that Price Waterhouse & Co "
        "Chartered Accountants LLP (PWC) has resigned."
    )
    assert propose_event_type(text) is None


def test_propose_event_type_none_for_unrelated_text() -> None:
    assert propose_event_type("The company held its annual general meeting on time.") is None


def test_propose_event_type_rpt_growth_with_two_period_amounts() -> None:
    # v2 requires numeric amounts for >= 2 periods near the RPT phrase,
    # not just the phrase itself (see the false-positive examples below).
    text = (
        "Related party transactions with XYZ Limited: "
        "Rs. 143.23 crore for the year ended March 2025, "
        "compared to Rs. 125.97 crore for the year ended March 2024."
    )
    assert propose_event_type(text) == "RPT_GROWTH"


def test_propose_event_type_rpt_phrase_alone_is_none() -> None:
    # Real false-positive pattern from gold review: RPT *policy*
    # boilerplate with no quantified amounts at all.
    text = (
        "Before entering related party transactions, necessary approvals are "
        "obtained from the Audit Committee and the Board, especially if Directors "
        "have vested interests."
    )
    assert propose_event_type(text) is None


def test_propose_event_type_audit_qual_emphasis_of_matter_is_none() -> None:
    # Real gold false-positive pattern: v1 wrongly treated "emphasis of
    # matter" as a qualification. Taxonomy v1.0: it is a separate,
    # lower-severity flag, never a qualification.
    text = (
        "our audit opinion on the consolidated financial statements.\n"
        "Emphasis of Matters\n"
        "We draw attention to Note 30(A)(a) of the consolidated financial "
        "statements relating to the demand orders of Rs. 1,385.47 crore."
    )
    assert propose_event_type(text) is None


def test_propose_event_type_audit_qual_real_qualification_still_matches() -> None:
    text = "In our opinion, except for the matter described, this is a qualified opinion."
    assert propose_event_type(text) == "AUDIT_QUAL"


def test_propose_event_type_pledge_up_never_proposed_from_free_text() -> None:
    # Per this phase's explicit instruction: PLEDGE_UP must come only
    # from structured shareholding/encumbrance numbers, never free text.
    text = "The promoter has pledged a significant portion of shares as encumbrance."
    assert propose_event_type(text) is None


def test_propose_event_type_id_exit_role_mismatch_is_none() -> None:
    # Real gold false-positive: a Non-Executive (not Independent)
    # Director's resignation must not trigger ID_EXIT.
    text = (
        "Mr. Anil Khanna (DIN: 01334483), a Non-Executive Director of the Company, "
        "has resigned as a Director of the Company due to personal reasons."
    )
    assert propose_event_type(text) is None


def test_propose_event_type_id_exit_real_cessation_still_matches() -> None:
    # Real gold true positive: "ceased to be" (not "resigned"), split
    # across a PDF line-wrap in the real text, with a date.
    text = (
        "During the year under review, none of the Independent Directors of "
        "the Company have resigned before the expiry of their respective term(s). "
        "Dr. Jairam Varadaraj and Nawshir Mirza ceased to \n"
        "be Non-Executive, Independent Director(s) of the \n"
        "Company effective July 21, 2024 upon completion of their tenure."
    )
    assert propose_event_type(text) == "ID_EXIT"


def test_propose_event_type_roster_table_different_people_is_none() -> None:
    # Real gold false-positive: a Company Secretary's resignation in one
    # numbered row must not combine with an unrelated Independent
    # Director's name in the next row to produce ID_EXIT.
    text = (
        "\x078\t\nMs. Janhavi Khele - Company Secretary (Resigned w.e.f. April 18, 2025)\n\t\n"
        "\x079\t\nMr. Ravi Shankar Gopinath - Independent Director\n\t\n"
        "\x0710\t\nMr. Shyamak Tata - Independent Director (w.e.f. October 17, 2023)\n\t\n"
        "\x0711\t\nMr. Parag Shah - Independent Director (w.e.f. December 12, 2024)"
    )
    assert propose_event_type(text) != "ID_EXIT"


def test_propose_event_type_roster_table_same_row_kmp_exit_matches() -> None:
    # Same fixture as the roster test above, kept at its real size (>= 3
    # numbered rows -- below that, _row_segments doesn't treat it as a
    # table at all and falls back to the window check, which is a
    # different code path this test isn't exercising). The Company
    # Secretary's own row is a genuine, same-row KMP_EXIT fact (name +
    # role + resignation language all in one numbered row).
    text = (
        "\x078\t\nMs. Janhavi Khele - Company Secretary (Resigned w.e.f. April 18, 2025)\n\t\n"
        "\x079\t\nMr. Ravi Shankar Gopinath - Independent Director\n\t\n"
        "\x0710\t\nMr. Shyamak Tata - Independent Director (w.e.f. October 17, 2023)\n\t\n"
    )
    assert propose_event_type(text) == "KMP_EXIT"


def test_propose_labels_is_idempotent(db_session: Session) -> None:
    import datetime as dt

    from ledgerlight.db.models import Document, DocumentVersion

    document = Document(source_id="sebi", source_key=f"test://{uuid.uuid4()}", document_type="x")
    db_session.add(document)
    db_session.flush()
    version = DocumentVersion(
        document_id=document.id,
        sha256=uuid.uuid4().hex + uuid.uuid4().hex,
        content_sha256=uuid.uuid4().hex + uuid.uuid4().hex,
        object_key="raw/test/test.pdf",
        bytes=100,
        mime_type="application/pdf",
        retrieval_method="automated_fetch",
        retrieval_url="https://example.com/test.pdf",
        retrieved_at=dt.datetime.now(dt.UTC),
        known_at=dt.datetime.now(dt.UTC),
        known_at_basis="retrieved_at",
        tool_version="test/1",
    )
    db_session.add(version)
    db_session.flush()

    chunk_ids = set()
    for i in range(20):
        chunk = Chunk(
            version_id=version.id,
            page_number=1,
            char_start=i * 10,
            char_end=i * 10 + 9,
            text="nothing relevant here at all",
            chunker_version="test-1",
            known_at=version.known_at,
        )
        db_session.add(chunk)
        db_session.flush()
        chunk_ids.add(chunk.id)

    # Scoped to only this test's own chunks -- never touches the real
    # corpus's chunks or label_items.
    first = propose_labels(db_session, none_sample_rate=3, only_chunk_ids=chunk_ids)
    second = propose_labels(db_session, none_sample_rate=3, only_chunk_ids=chunk_ids)

    assert first.chunks_seen == 20
    assert first.proposals_created > 0
    assert second.proposals_created == 0
    assert second.already_proposed == first.proposals_created
