"""OCR fallback for scanned pages — RapidOCR (ONNXRuntime backend).

Chosen over Tesseract because Tesseract has no installer that works
without admin rights on this Windows environment (verified: the official
UB-Mannheim NSIS installer requires elevation even for a custom install
directory — see docs/phase-1/phase-1-report.md). RapidOCR is a pure
pip-installable, CPU-only, ONNX-based engine with bundled models (no
network call at runtime), matching the brief's explicit fallback
("a pip-installable CPU engine such as docTR or PaddleOCR, in an optional
dependency group") in spirit even though it isn't literally one of those
two named packages.

Optional dependency group: `ocr` (`uv sync --extra ocr`).
"""

from __future__ import annotations

import numpy as np

OCR_ENGINE_NAME = "rapidocr-onnxruntime"


class OcrUnavailableError(RuntimeError):
    """Raised if the `ocr` optional dependency group isn't installed."""


def _engine_version() -> str:
    from importlib.metadata import version

    return version("rapidocr-onnxruntime")


def run_ocr(image: np.ndarray) -> tuple[str, float]:
    """Returns (concatenated text, mean confidence across detected lines).

    Returns ("", 0.0) if no text is detected — that is a valid, non-error
    result (a blank or purely graphical page).
    """
    try:
        from rapidocr_onnxruntime import RapidOCR
    except ImportError as exc:
        raise OcrUnavailableError(
            "rapidocr-onnxruntime is not installed — run `uv sync --extra ocr`"
        ) from exc

    engine = RapidOCR()
    result, _elapse = engine(image)
    if not result:
        return "", 0.0

    lines = [r[1] for r in result]
    confidences = [float(r[2]) for r in result]
    text = "\n".join(lines)
    mean_confidence = sum(confidences) / len(confidences)
    return text, mean_confidence
