"""PDF text extraction (PyMuPDF), with a tested heuristic for which pages
need OCR instead of (or in addition to) their native text layer.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pymupdf

from ledgerlight.processing.limits import ProcessingLimits, check_page_count

EXTRACTOR_VERSION = "pdf-pymupdf-1"

# A page "needs OCR" when it has very little native text AND is
# image-dominant — i.e. it looks like a scan, not a sparsely-worded page
# (annual-report cover pages, section dividers etc. can have few
# characters but are NOT scans; they just don't have much text, and
# running OCR on them would find nothing new). Both conditions are
# required, per the real-corpus probe in docs/ingestion/architecture.md
# that found numerous low-text pages which were graphic design, not scans.
OCR_CHAR_THRESHOLD = 200
OCR_MIN_IMAGE_AREA_RATIO = 0.85
OCR_MAX_IMAGE_COUNT = 3


@dataclass(frozen=True)
class ExtractedPage:
    page_number: int  # 1-based
    raw_text: str
    char_count: int
    needs_ocr: bool
    extraction_method: str  # "text_layer" (even if needs_ocr is also True — OCR augments it)


def page_needs_ocr(char_count: int, image_count: int, max_image_area_ratio: float) -> bool:
    """The tested heuristic, extracted as a pure function of three cheap
    per-page measurements so it can be unit tested without a real PDF."""
    return (
        char_count < OCR_CHAR_THRESHOLD
        and image_count <= OCR_MAX_IMAGE_COUNT
        and max_image_area_ratio > OCR_MIN_IMAGE_AREA_RATIO
    )


def extract_pdf_pages(path_or_bytes: str | bytes, limits: ProcessingLimits) -> list[ExtractedPage]:
    doc = (
        pymupdf.open(stream=path_or_bytes, filetype="pdf")
        if isinstance(path_or_bytes, bytes)
        else pymupdf.open(path_or_bytes)
    )
    try:
        check_page_count(doc.page_count, limits)
        pages: list[ExtractedPage] = []
        for i, page in enumerate(doc):
            text = page.get_text()
            char_count = len(text.strip())

            page_area = page.rect.width * page.rect.height
            image_infos = page.get_image_info()
            max_ratio = 0.0
            if page_area:
                for info in image_infos:
                    bbox = info["bbox"]
                    area = max(0.0, bbox[2] - bbox[0]) * max(0.0, bbox[3] - bbox[1])
                    max_ratio = max(max_ratio, area / page_area)

            needs_ocr = page_needs_ocr(char_count, len(image_infos), max_ratio)

            pages.append(
                ExtractedPage(
                    page_number=i + 1,
                    raw_text=text,
                    char_count=char_count,
                    needs_ocr=needs_ocr,
                    extraction_method="text_layer",
                )
            )
        return pages
    finally:
        doc.close()


def render_page_to_rgb_array(
    path_or_bytes: str | bytes, page_number: int, zoom: float = 2.0
) -> np.ndarray:
    """Render one page (1-based) to a numpy RGB array for OCR input."""
    doc = (
        pymupdf.open(stream=path_or_bytes, filetype="pdf")
        if isinstance(path_or_bytes, bytes)
        else pymupdf.open(path_or_bytes)
    )
    try:
        page = doc[page_number - 1]
        mat = pymupdf.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat, colorspace=pymupdf.csRGB)
        arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
        return arr
    finally:
        doc.close()
