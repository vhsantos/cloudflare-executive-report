"""ReportLab paragraph styles."""

from __future__ import annotations

from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet

from cloudflare_executive_report.pdf.theme import Theme


def build_styles(theme: Theme) -> Any:
    base = getSampleStyleSheet()
    base.add(
        ParagraphStyle(
            name="RepH1",
            fontName="Helvetica-Bold",
            fontSize=theme.title_size,
            leading=theme.title_size + 4,
            spaceAfter=4,
            textColor=colors.HexColor(theme.slate),
        )
    )
    base.add(
        ParagraphStyle(
            name="RepOverline",
            fontName="Helvetica-Bold",
            fontSize=9,
            leading=11,
            spaceAfter=2,
            textColor=colors.HexColor(theme.primary),
        )
    )
    base.add(
        ParagraphStyle(
            name="RepSubtitle",
            fontName="Helvetica",
            fontSize=9.5,
            leading=13,
            spaceAfter=14,
            textColor=colors.HexColor(theme.muted),
        )
    )
    base.add(
        ParagraphStyle(
            name="RepStreamHeadLeft",
            fontName="Helvetica-Bold",
            fontSize=theme.title_size,
            leading=theme.title_size + 4,
            textColor=colors.HexColor(theme.section_blue),
            alignment=TA_LEFT,
            spaceBefore=0,
            spaceAfter=0,
        )
    )
    base.add(
        ParagraphStyle(
            name="RepStreamHeadRight",
            parent=base["RepSubtitle"],
            alignment=TA_RIGHT,
            spaceBefore=0,
            spaceAfter=0,
        )
    )
    base.add(
        ParagraphStyle(
            name="RepSection",
            fontName="Helvetica-Bold",
            fontSize=theme.section_size,
            leading=14,
            spaceBefore=2,
            spaceAfter=8,
            textColor=colors.HexColor(theme.section_blue),
        )
    )
    base.add(
        ParagraphStyle(
            name="RepSectionTight",
            parent=base["RepSection"],
            spaceBefore=0,
            spaceAfter=0,
        )
    )
    base.add(
        ParagraphStyle(
            name="RepCardTitle",
            parent=base["RepSection"],
            spaceBefore=0,
            spaceAfter=0,
        )
    )
    base.add(
        ParagraphStyle(
            name="RepKpiLabel",
            fontName="Helvetica",
            fontSize=8.5,
            leading=10,
            textColor=colors.HexColor(theme.muted),
        )
    )
    base.add(
        ParagraphStyle(
            name="RepKpiValue",
            fontName="Helvetica-Bold",
            fontSize=20,
            leading=24,
            textColor=colors.HexColor(theme.slate),
        )
    )
    base.add(
        ParagraphStyle(
            name="RepKpiLabelCenter",
            parent=base["RepKpiLabel"],
            alignment=TA_CENTER,
        )
    )
    base.add(
        ParagraphStyle(
            name="RepKpiValueCenter",
            parent=base["RepKpiValue"],
            alignment=TA_CENTER,
        )
    )
    base.add(
        ParagraphStyle(
            name="RepTableHead",
            fontName="Helvetica-Bold",
            fontSize=9,
            leading=11,
            textColor=colors.HexColor(theme.muted),
        )
    )
    base.add(
        ParagraphStyle(
            name="RepTableCell",
            fontName="Helvetica",
            fontSize=8,
            leading=10,
            textColor=colors.HexColor(theme.slate),
        )
    )
    base.add(
        ParagraphStyle(
            name="RepFootnote",
            fontName="Helvetica",
            fontSize=8,
            leading=10,
            textColor=colors.HexColor(theme.muted),
        )
    )
    base.add(
        ParagraphStyle(
            name="RepZoneTitle",
            fontName="Helvetica-Bold",
            fontSize=14,
            leading=18,
            spaceAfter=12,
            textColor=colors.HexColor(theme.slate),
        )
    )
    return base
