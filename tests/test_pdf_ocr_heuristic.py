"""Unit tests for the pure OCR-needed heuristic (ledgerlight.processing.pdf
.page_needs_ocr). Refined from a naive "low char count" check after real
corpus probing (see docs/data/temporal-semantics.md's sibling note in
docs/ingestion/architecture.md) found graphic-design-heavy annual-report
pages that would have false-triggered it — this file pins both the
original scanned-page case and the false-trigger cases it was fixed for."""

from __future__ import annotations

from ledgerlight.processing.pdf import page_needs_ocr


def test_scanned_looking_page_needs_ocr() -> None:
    # Almost no text, one dominant full-page image.
    assert page_needs_ocr(char_count=12, image_count=1, max_image_area_ratio=0.98) is True


def test_normal_text_page_does_not_need_ocr() -> None:
    assert page_needs_ocr(char_count=2000, image_count=0, max_image_area_ratio=0.0) is False


def test_graphic_design_cover_page_with_little_text_but_many_images_is_not_ocr() -> None:
    # Real corpus case: a cover page with 27 chars and 55 small images is a
    # design layout, not a scan -- the image COUNT cap is what rules it out.
    assert page_needs_ocr(char_count=27, image_count=55, max_image_area_ratio=0.95) is False


def test_divider_page_with_many_tiny_images_is_not_ocr() -> None:
    # Real corpus case: 23 chars, 271 images (icons/decoration), still not a scan.
    assert page_needs_ocr(char_count=23, image_count=271, max_image_area_ratio=0.9) is False


def test_low_text_but_small_image_is_not_ocr() -> None:
    # Low text, one image, but the image doesn't dominate the page -- e.g.
    # a mostly-blank page with a small logo.
    assert page_needs_ocr(char_count=10, image_count=1, max_image_area_ratio=0.2) is False


def test_text_heavy_page_with_one_large_image_is_not_ocr() -> None:
    # Plenty of real text alongside a large figure -- not a scan.
    assert page_needs_ocr(char_count=1500, image_count=1, max_image_area_ratio=0.9) is False
