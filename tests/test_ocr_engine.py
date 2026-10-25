"""Exercises the real OCR engine (RapidOCR, see
ledgerlight.processing.ocr) end-to-end against a SYNTHETIC fixture --
tests/fixtures/synthetic_scanned_page.pdf is a hand-generated "scanned
page" (a raster image of text with no PDF text layer), never a real
downloaded document. See scripts in docs/ingestion/architecture.md for how
it was made.

Real-corpus note: probing the full Phase 0/Correction 1 corpus (237
documents) found zero genuinely scanned pages -- every low-text page
turned out to be a graphic-design layout (cover/divider pages), not a
scan. This fixture is what proves the OCR code path actually works,
since the real corpus never exercises it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ledgerlight.processing import pdf as pdf_mod
from ledgerlight.processing.limits import ProcessingLimits
from ledgerlight.processing.ocr import OcrUnavailableError, run_ocr

FIXTURE = Path(__file__).parent / "fixtures" / "synthetic_scanned_page.pdf"


def test_fixture_exists() -> None:
    assert FIXTURE.exists(), "run the fixture generator if this is missing"


def test_extract_pdf_pages_flags_synthetic_scan_for_ocr() -> None:
    pages = pdf_mod.extract_pdf_pages(str(FIXTURE), ProcessingLimits())
    assert len(pages) == 1
    assert pages[0].needs_ocr is True
    assert pages[0].raw_text == ""  # no text layer at all


def test_ocr_extracts_recognisable_text_from_synthetic_scan() -> None:
    try:
        image = pdf_mod.render_page_to_rgb_array(str(FIXTURE), 1)
        text, mean_confidence = run_ocr(image)
    except OcrUnavailableError:
        pytest.skip("OCR engine (rapidocr-onnxruntime) not installed in this environment")

    assert "SYNTHETIC" in text.upper()
    assert "123456789" in text
    assert mean_confidence > 0.5
