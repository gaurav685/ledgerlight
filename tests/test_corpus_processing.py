"""Tests against the real downloaded corpus (data/raw/) -- never committed
(see .gitignore), so these skip cleanly in any environment that hasn't run
the acquisition/ingestion scripts. Validates real-world behaviour that a
synthetic fixture can't: actual NSE bhavcopy files parse cleanly, and the
OCR heuristic doesn't false-trigger on real annual-report pages.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from ledgerlight.processing import pdf as pdf_mod
from ledgerlight.processing.bhavcopy import parse_bhavcopy_csv
from ledgerlight.processing.limits import ProcessingLimits

pytestmark = pytest.mark.corpus

DATA_RAW = Path(__file__).resolve().parent.parent / "data" / "raw"


def _real_bhavcopy_zips() -> list[Path]:
    nse_dir = DATA_RAW / "nse_archives"
    if not nse_dir.exists():
        return []
    return sorted(nse_dir.rglob("*.zip"))


def _real_pdfs() -> list[Path]:
    if not DATA_RAW.exists():
        return []
    return sorted(DATA_RAW.rglob("*.pdf"))


def test_real_bhavcopy_files_parse_with_low_quarantine_rate() -> None:
    zips = _real_bhavcopy_zips()
    if not zips:
        pytest.skip("data/raw/nse_archives has no bhavcopy files -- run acquisition first")

    total_rows = 0
    total_quarantined = 0
    sample = zips[:25]  # bounded -- this is a sanity check, not a full re-parse
    for zpath in sample:
        with zipfile.ZipFile(zpath) as zf:
            names = zf.namelist()
            assert len(names) == 1
            csv_text = zf.read(names[0]).decode("utf-8")
        result = parse_bhavcopy_csv(csv_text)
        total_rows += len(result.rows)
        total_quarantined += len(result.quarantined)

    assert total_rows > 0
    quarantine_rate = total_quarantined / (total_rows + total_quarantined)
    assert quarantine_rate < 0.01, (
        f"unexpectedly high quarantine rate {quarantine_rate:.4f} across "
        f"{len(sample)} real bhavcopy files"
    )


def test_real_corpus_has_no_genuinely_scanned_pdf_pages() -> None:
    """Documents the real finding (not assumed): probing every PDF page in
    the ingested corpus for the OCR heuristic found zero genuine scans --
    every low-text page is a graphic-design layout. If this ever fails, it
    means a real scanned page finally showed up, which is useful to know,
    not a bug -- see tests/test_ocr_engine.py for the synthetic fixture
    that actually proves the OCR path works."""
    pdfs = _real_pdfs()
    if not pdfs:
        pytest.skip("data/raw has no PDFs -- run acquisition first")

    limits = ProcessingLimits()
    ocr_needed_pages: list[str] = []
    for pdf_path in pdfs:
        try:
            pages = pdf_mod.extract_pdf_pages(str(pdf_path), limits)
        except Exception:  # noqa: BLE001 - a handful of real files may be unreadable; skip them
            continue
        for page in pages:
            if page.needs_ocr:
                ocr_needed_pages.append(f"{pdf_path.name}:page{page.page_number}")

    assert ocr_needed_pages == [], (
        f"found {len(ocr_needed_pages)} page(s) now flagged as needing OCR in the real "
        f"corpus (previously zero): {ocr_needed_pages[:10]}"
    )
