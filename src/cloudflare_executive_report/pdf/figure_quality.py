"""Raster DPI presets for PDF maps and charts (from config ``pdf_image_quality``)."""

from __future__ import annotations

from dataclasses import replace
from enum import StrEnum

from cloudflare_executive_report.pdf.theme import DEFAULT_THEME, Theme


class PdfFigureQuality(StrEnum):
    """Trade-off between PDF file size and sharpness of embedded matplotlib PNGs."""

    low = "low"
    medium = "medium"
    high = "high"


# (chart_dpi, map_dpi) - common screen steps: 72 / 96 / 130 (high for sharper maps & charts).
_PDF_IMAGE_QUALITY_DPIS: dict[PdfFigureQuality, tuple[int, int]] = {
    PdfFigureQuality.low: (72, 72),
    PdfFigureQuality.medium: (96, 96),
    PdfFigureQuality.high: (130, 130),
}


def parse_pdf_image_quality(raw: str | None) -> PdfFigureQuality:
    s = (raw or "high").strip().lower()
    try:
        return PdfFigureQuality(s)
    except ValueError as e:
        msg = f"pdf_image_quality must be low, medium, or high (got {raw!r})"
        raise ValueError(msg) from e


def theme_with_pdf_image_quality(
    quality: PdfFigureQuality,
    base: Theme | None = None,
) -> Theme:
    """Return ``base`` (or default theme) with ``chart_dpi`` / ``map_dpi`` for ``quality``."""
    b = base or DEFAULT_THEME
    cd, md = _PDF_IMAGE_QUALITY_DPIS[quality]
    return replace(b, chart_dpi=cd, map_dpi=md)
