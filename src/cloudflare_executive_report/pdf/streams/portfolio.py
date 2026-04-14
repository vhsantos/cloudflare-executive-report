"""Multi-zone portfolio summary page."""

from __future__ import annotations

from typing import Any

from reportlab.lib import colors
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

from cloudflare_executive_report.common.constants import (
    PDF_SPACE_MEDIUM_PT,
    PDF_TABLE_BOX_LINE_PT,
    PDF_TABLE_CELL_PAD_X_PT,
    PDF_TABLE_CELL_PAD_Y_PT,
    PDF_TABLE_INNER_GRID_LINE_PT,
)
from cloudflare_executive_report.common.formatting import format_number_compact
from cloudflare_executive_report.executive.portfolio import (
    GRADE_BAND_LABELS,
    GRADE_ORDER,
    PortfolioSummary,
)
from cloudflare_executive_report.pdf.primitives import get_render_context
from cloudflare_executive_report.pdf.theme import Theme


def _zone_word(count: int) -> str:
    return "zone" if count == 1 else "zones"


def _portfolio_table(
    rows: list[list[str]],
    *,
    col_widths: list[int],
    theme: Theme,
    center_columns: tuple[int, ...],
) -> Table:
    table = Table(rows, colWidths=col_widths)
    last_row = len(rows) - 1
    style_cmds: list[tuple[Any, ...]] = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(theme.accent)),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8),
        ("FONT", (0, 1), (-1, -1), "Helvetica", 8),
        ("TEXTCOLOR", (0, 1), (-1, -1), colors.HexColor(theme.slate)),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor(theme.row_alt)]),
        ("BOX", (0, 0), (-1, -1), PDF_TABLE_BOX_LINE_PT, colors.HexColor(theme.border)),
        (
            "INNERGRID",
            (0, 0),
            (-1, -1),
            PDF_TABLE_INNER_GRID_LINE_PT,
            colors.HexColor(theme.border),
        ),
        ("LEFTPADDING", (0, 0), (-1, -1), PDF_TABLE_CELL_PAD_X_PT),
        ("RIGHTPADDING", (0, 0), (-1, -1), PDF_TABLE_CELL_PAD_X_PT),
        ("TOPPADDING", (0, 0), (-1, -1), PDF_TABLE_CELL_PAD_Y_PT),
        ("BOTTOMPADDING", (0, 0), (-1, -1), PDF_TABLE_CELL_PAD_Y_PT),
    ]
    for col in center_columns:
        style_cmds.append(("ALIGN", (col, 0), (col, last_row), "CENTER"))
    table.setStyle(TableStyle(style_cmds))
    return table


def _append_zone_scores_table(
    story: list[Any],
    summary: PortfolioSummary,
    *,
    theme: Theme,
) -> None:
    styles = get_render_context().styles
    story.append(
        Paragraph(
            f"Zones (sorted by {summary.zones_sort_caption})",
            styles["RepSection"],
        )
    )
    rows: list[list[str]] = [["Zone", "Score", "Grade", "Critical Risks", "Warnings"]]
    for row in summary.zones:
        rows.append(
            [
                row.zone_name,
                format_number_compact(row.security_score),
                row.security_grade,
                str(row.critical_risks),
                str(row.warning_risks),
            ]
        )
    story.append(
        _portfolio_table(
            rows,
            col_widths=[200, 55, 45, 95, 85],
            theme=theme,
            center_columns=(1, 2, 3, 4),
        )
    )


def _append_common_risks_table(
    story: list[Any], summary: PortfolioSummary, *, theme: Theme
) -> None:
    styles = get_render_context().styles
    story.append(Spacer(1, PDF_SPACE_MEDIUM_PT))
    story.append(Paragraph("Common risks (count of zones affected)", styles["RepSection"]))
    rows: list[list[str]] = [["Risk", "Zones"]]
    for row in summary.common_risks[:10]:
        rows.append(
            [
                f"{row.phrase_text} ({row.check_id})",
                f"{row.zone_count} {_zone_word(row.zone_count)}",
            ]
        )
    if len(rows) == 1:
        rows.append(["No shared risks detected.", "-"])
    story.append(
        _portfolio_table(
            rows,
            col_widths=[395, 85],
            theme=theme,
            center_columns=(1,),
        )
    )


def _append_grade_distribution(
    story: list[Any], summary: PortfolioSummary, *, theme: Theme
) -> None:
    styles = get_render_context().styles
    grade_counts = summary.grade_distribution
    story.append(Spacer(1, PDF_SPACE_MEDIUM_PT))
    story.append(Paragraph("Grade distribution", styles["RepSection"]))
    rows: list[list[str]] = [["Band", "Zones"]]
    for grade in GRADE_ORDER:
        band = GRADE_BAND_LABELS[grade]
        count = grade_counts.get(grade, 0)
        rows.append([band, f"{count} zones"])
    story.append(
        _portfolio_table(
            rows,
            col_widths=[395, 85],
            theme=theme,
            center_columns=(1,),
        )
    )


def append_portfolio_summary(
    story: list[Any],
    *,
    summary: PortfolioSummary,
    period_start: str,
    period_end: str,
    theme: Theme,
) -> None:
    """Append one multi-zone portfolio page."""
    styles = get_render_context().styles
    story.append(Paragraph("Multi-Zone Security Summary", styles["RepStreamHeadLeft"]))
    story.append(
        Paragraph(
            f"<font color='{theme.muted}'>{period_start} to {period_end} (UTC)</font>",
            styles["RepSubtitle"],
        )
    )
    _append_zone_scores_table(story, summary, theme=theme)
    _append_common_risks_table(story, summary, theme=theme)
    _append_grade_distribution(story, summary, theme=theme)
