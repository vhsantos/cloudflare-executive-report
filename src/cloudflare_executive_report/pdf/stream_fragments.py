"""Shared ReportLab snippets used by multiple analytics streams."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Any

from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

from cloudflare_executive_report.pdf.charts import prepare_daily_metric_series
from cloudflare_executive_report.pdf.primitives import figure_from_bytes
from cloudflare_executive_report.pdf.theme import Theme


def append_stream_header(
    story: list[Any],
    styles: Any,
    theme: Theme,
    blocks: set[str],
    *,
    stream_title: str,
    zone_name: str,
    period_start: str,
    period_end: str,
) -> None:
    if "header" not in blocks:
        return
    w = theme.content_width_in() * inch
    left_w = w * 0.38
    right_w = w * 0.62
    left_p = Paragraph(stream_title, styles["RepStreamHeadLeft"])
    right_p = Paragraph(
        f"<font color='{theme.primary}'><b>{zone_name}</b></font>"
        f"<font color='{theme.muted}'> · {period_start} to {period_end} (UTC)</font>",
        styles["RepStreamHeadRight"],
    )
    head = Table([[left_p, right_p]], colWidths=[left_w, right_w])
    head.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    story.append(head)
    story.append(Spacer(1, 14))


def append_missing_dates_note(
    story: list[Any],
    styles: Any,
    blocks: set[str],
    missing_dates: list[str],
) -> None:
    if not missing_dates or "header" not in blocks:
        return
    miss_note = ", ".join(missing_dates[:12])
    if len(missing_dates) > 12:
        miss_note += ", …"
    story.append(
        Paragraph(
            f"<i>Missing data for {len(missing_dates)} day(s): {miss_note}</i>",
            styles["RepFootnote"],
        )
    )
    story.append(Spacer(1, 8))


def append_timeseries_if_enabled(
    story: list[Any],
    styles: Any,
    theme: Theme,
    blocks: set[str],
    daily_points: Sequence[tuple[date, int | None]],
    *,
    chart_title: str,
    y_axis_label: str,
) -> None:
    if "timeseries" not in blocks:
        return
    png, sub = prepare_daily_metric_series(
        daily_points,
        theme,
        chart_title=chart_title,
        y_axis_label=y_axis_label,
    )
    if not png:
        return
    w_content = theme.content_width_in()
    story.append(Spacer(1, 14))
    story.append(Paragraph("Time series", styles["RepSection"]))
    if sub:
        story.append(Paragraph(f"<i>{sub}</i>", styles["RepFootnote"]))
    tw = min(w_content, 7.1)
    th = tw * 0.38
    story.append(figure_from_bytes(png, width_in=tw, height_in=th))


def append_png_chart_section(
    story: list[Any],
    styles: Any,
    theme: Theme,
    blocks: set[str],
    *,
    heading: str,
    png: bytes,
    subtitle: str = "",
) -> None:
    """Append a titled chart image when ``timeseries`` is enabled and ``png`` is non-empty."""
    if "timeseries" not in blocks or not png:
        return
    w_content = theme.content_width_in()
    story.append(Spacer(1, 14))
    story.append(Paragraph(heading, styles["RepSection"]))
    if subtitle:
        story.append(Paragraph(f"<i>{subtitle}</i>", styles["RepFootnote"]))
    tw = min(w_content, 7.1)
    th = tw * 0.38
    story.append(figure_from_bytes(png, width_in=tw, height_in=th))
