"""SimpleDocTemplate factory and footer drawing."""

from __future__ import annotations

from functools import partial
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate

from cloudflare_executive_report.pdf.theme import Theme


def build_simple_doc(
    output_path: str,
    *,
    theme: Theme,
    title: str = "Analytics report",
) -> SimpleDocTemplate:
    return SimpleDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=theme.margin_in * inch,
        rightMargin=theme.margin_in * inch,
        topMargin=theme.top_margin_in * inch,
        bottomMargin=theme.bottom_margin_in * inch,
        title=title,
    )


def draw_report_footer(
    canvas_obj: Any,
    doc: Any,
    *,
    theme: Theme,
    left_text: str,
) -> None:
    canvas_obj.saveState()
    canvas_obj.setFont("Helvetica", 8)
    canvas_obj.setFillColor(colors.HexColor(theme.muted))
    canvas_obj.drawString(theme.margin_in * inch, 0.42 * inch, left_text)
    page_w = doc.pagesize[0]
    canvas_obj.drawRightString(
        page_w - theme.margin_in * inch,
        0.42 * inch,
        f"Page {canvas_obj.getPageNumber()}",
    )
    canvas_obj.restoreState()


def footer_canvas_factory(*, theme: Theme, left_text: str):
    return partial(
        draw_report_footer,
        theme=theme,
        left_text=left_text,
    )
