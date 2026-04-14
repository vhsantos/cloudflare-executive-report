"""SimpleDocTemplate factory and footer drawing."""

from __future__ import annotations

from functools import partial
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate

from cloudflare_executive_report.common.constants import PDF_TOP_ACCENT_BAR_HEIGHT_PT
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


def draw_report_chrome(
    canvas_obj: Any,
    doc: Any,
    *,
    theme: Theme,
    left_text: str,
) -> None:
    canvas_obj.saveState()
    # This callback draws footer text and page-level chrome; top accent strip is intentional.
    if canvas_obj.getPageNumber() > 1:
        page_w = doc.pagesize[0]
        page_h = doc.pagesize[1]
        canvas_obj.setFillColor(colors.HexColor(theme.accent))
        canvas_obj.rect(
            0,
            page_h - PDF_TOP_ACCENT_BAR_HEIGHT_PT,
            page_w,
            PDF_TOP_ACCENT_BAR_HEIGHT_PT,
            fill=1,
            stroke=0,
        )
    footer_rule_y = 0.62 * inch
    canvas_obj.setStrokeColor(colors.HexColor(theme.border))
    canvas_obj.setLineWidth(0.5)
    canvas_obj.line(
        theme.margin_in * inch,
        footer_rule_y,
        doc.pagesize[0] - theme.margin_in * inch,
        footer_rule_y,
    )
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
        draw_report_chrome,
        theme=theme,
        left_text=left_text,
    )
