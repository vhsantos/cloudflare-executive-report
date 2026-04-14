"""Visual tokens and page metrics for PDF reports."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import inch


@dataclass(frozen=True)
class Theme:
    primary: str = "#2563eb"
    accent: str = "#f38020"
    mitigated: str = "#16a34a"
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
    chart_format: Literal["png", "svg"] = "png"
    map_format: Literal["png", "svg"] = "png"
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


def theme_with_chart_format(theme: Theme, chart_format: Literal["png", "svg"]) -> Theme:
    """Return ``theme`` with validated chart format (png or svg)."""
    if chart_format == theme.chart_format:
        return theme
    return replace(theme, chart_format=chart_format)


def theme_with_map_format(theme: Theme, map_format: Literal["png", "svg"]) -> Theme:
    """Return ``theme`` with validated map format (png or svg)."""
    if map_format == theme.map_format:
        return theme
    return replace(theme, map_format=map_format)


def theme_with_brand_colors(theme: Theme, *, primary: str, accent: str) -> Theme:
    """Return theme with report-level primary/accent color overrides."""
    if primary == theme.primary and accent == theme.accent:
        return theme
    return replace(theme, primary=primary, accent=accent)
