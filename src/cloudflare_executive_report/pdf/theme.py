"""Visual tokens and page metrics for PDF reports."""

from __future__ import annotations

from dataclasses import dataclass

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import inch


@dataclass(frozen=True)
class Theme:
    primary: str = "#2563eb"
    slate: str = "#0f172a"
    muted: str = "#64748b"
    border: str = "#e2e8f0"
    row_alt: str = "#f8fafc"
    card_bg: str = "#ffffff"
    section_blue: str = "#1e40af"
    bar_track: str = "#e2e8f0"
    margin_in: float = 0.5
    top_margin_in: float = 0.5
    bottom_margin_in: float = 0.5
    col_gap_in: float = 0.14
    outer_card_pad_pt: float = 10.0
    # Defaults match ``pdf_image_quality: medium`` (96); PDF build applies preset from config.
    chart_dpi: int = 96
    map_dpi: int = 96
    title_size: int = 22
    section_size: int = 11

    def content_width_in(self) -> float:
        page_w_in = A4[0] / inch
        return page_w_in - 2 * self.margin_in

    def half_inner_width_in(self) -> float:
        return self.content_width_in() / 2.0 - self.col_gap_in / 2.0

    def third_inner_width_in(self) -> float:
        """Width per column for a 3-up row (two gutters between three columns)."""
        return (self.content_width_in() - 2.0 * self.col_gap_in) / 3.0


DEFAULT_THEME = Theme()
