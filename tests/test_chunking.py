"""Chunking tests: char spans round-trip exactly to the page's raw_text,
and no chunk crosses a page boundary (enforced by construction --
chunk_page_text only ever sees one page's text)."""

from __future__ import annotations

from ledgerlight.knowledge.chunking import MAX_CHUNK_CHARS, chunk_page_text


def test_empty_page_produces_no_chunks() -> None:
    assert chunk_page_text("") == []


def test_short_page_is_a_single_chunk() -> None:
    text = "Hello world.\n\nThis is a short page."
    spans = chunk_page_text(text)
    assert len(spans) == 1
    assert spans[0].char_start == 0
    assert spans[0].char_end == len(text)


def test_spans_round_trip_exactly_to_the_source_text() -> None:
    text = (
        "Paragraph one with some content.\n\n"
        "Paragraph two with different content.\n\n"
        "Paragraph three."
    )
    spans = chunk_page_text(text)
    for span in spans:
        assert text[span.char_start : span.char_end] == span.text


def test_spans_are_ordered_and_non_overlapping_for_packed_paragraphs() -> None:
    text = "A" * 100 + "\n\n" + "B" * 100 + "\n\n" + "C" * 100
    spans = chunk_page_text(text)
    for i in range(len(spans) - 1):
        assert spans[i].char_end <= spans[i + 1].char_start


def test_long_paragraph_is_hard_split_with_overlap() -> None:
    text = "X" * (MAX_CHUNK_CHARS + 500)
    spans = chunk_page_text(text)
    assert len(spans) > 1
    for span in spans:
        assert text[span.char_start : span.char_end] == span.text
    # overlap: consecutive hard-split spans share some characters
    assert spans[1].char_start < spans[0].char_end


def test_many_small_paragraphs_get_packed_up_to_target() -> None:
    paragraphs = [f"Paragraph {i} content here." for i in range(50)]
    text = "\n\n".join(paragraphs)
    spans = chunk_page_text(text)
    # packed into far fewer chunks than paragraphs
    assert len(spans) < len(paragraphs)
    for span in spans:
        assert text[span.char_start : span.char_end] == span.text


def test_chunk_text_is_never_empty() -> None:
    text = "Real content.\n\n\n\nMore content after blank lines."
    spans = chunk_page_text(text)
    for span in spans:
        assert span.text != ""
        assert span.char_end > span.char_start
