"""Shared ReportLab snippets used by multiple analytics streams."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Any

from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

from cloudflare_executive_report.common.constants import (
    PDF_MAP_SIDE_BY_SIDE_MAP_WIDTH_SHARE,
    PDF_SPACE_MEDIUM_PT,
    PDF_SPACE_SMALL_PT,
)
from cloudflare_executive_report.pdf.charts import prepare_single_line_daily_series
from cloudflare_executive_report.pdf.maps import map_height_in_for_width
from cloudflare_executive_report.pdf.primitives import (
    figure_from_bytes,
    map_side_by_side_table,
    table_with_bars,
)
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
    story.append(Spacer(1, PDF_SPACE_MEDIUM_PT))


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
    story.append(Spacer(1, PDF_SPACE_MEDIUM_PT))


def append_timeseries_if_enabled(
    story: list[Any],
    styles: Any,
    theme: Theme,
    blocks: set[str],
    daily_points: Sequence[tuple[date, int | None]],
    *,
    chart_title: str,
    y_axis_label: str,
    heading: str | None = "Time series",
) -> None:
    """Build a single-line daily chart from points and append it when timeseries is enabled."""
    if "timeseries" not in blocks:
        return
    chart_bytes, sub = prepare_single_line_daily_series(
        daily_points,
        theme,
        chart_title=chart_title,
        y_axis_label=y_axis_label,
    )
    append_chart_section(
        story,
        styles,
        theme,
        blocks,
        heading=heading,
        chart_bytes=chart_bytes,
        subtitle=sub,
    )


def append_chart_section(
    story: list[Any],
    styles: Any,
    theme: Theme,
    blocks: set[str],
    *,
    heading: str | None = None,
    chart_bytes: bytes,
    subtitle: str = "",
) -> None:
    """Append a chart image when ``timeseries`` is enabled and bytes are non-empty."""
    if "timeseries" not in blocks or not chart_bytes:
        return
    w_content = theme.content_width_in()
    if heading:
        story.append(Paragraph(heading, styles["RepSection"]))
    if subtitle:
        story.append(Paragraph(f"<i>{subtitle}</i>", styles["RepFootnote"]))
    tw = w_content - (10.0 / inch)
    th = tw * 0.33
    story.append(figure_from_bytes(chart_bytes, width_in=tw, height_in=th))


def append_prepared_timeseries_chart(
    story: list[Any],
    styles: Any,
    theme: Theme,
    blocks: set[str],
    chart_bytes: bytes,
    subtitle: str = "",
) -> None:
    """Append a pre-rendered timeseries PNG via ``append_chart_section`` (no section heading)."""
    append_chart_section(
        story,
        styles,
        theme,
        blocks,
        heading=None,
        chart_bytes=chart_bytes,
        subtitle=subtitle,
    )


def append_map_and_ranked_table(
    story: list[Any],
    styles: Any,
    theme: Theme,
    blocks: set[str],
    *,
    map_block_name: str,
    table_block_name: str,
    table_rows_side: list[list[Any]],
    table_rows_full: list[list[Any]],
    table_title: str,
    side_table_ratios: tuple[float, float, float],
    full_table_ratios: tuple[float, float, float],
    build_map_image_for_width: Any,
    append_space_after_table_only: bool = False,
) -> None:
    """Append shared world-map + ranked-table section used by multiple streams."""
    w_content = theme.content_width_in()
    map_frac = PDF_MAP_SIDE_BY_SIDE_MAP_WIDTH_SHARE
    side_table_w_in = w_content * (1.0 - map_frac)
    has_map = map_block_name in blocks
    has_table = table_block_name in blocks
    map_width_in = w_content * map_frac if has_table and table_rows_side else w_content
    map_image_bytes = b""
    if has_map:
        map_image_bytes = build_map_image_for_width(map_width_in)

    if map_image_bytes and has_table and table_rows_side:
        map_h = map_height_in_for_width(map_width_in)
        map_fig = figure_from_bytes(map_image_bytes, width_in=map_width_in, height_in=map_h)
        side_table = table_with_bars(
            table_title,
            table_rows_side,
            side_table_ratios,
            total_width_in=side_table_w_in,
            show_outer_card=False,
        )
        story.append(map_side_by_side_table(map_fig, side_table, content_width_in=w_content))
        story.append(Spacer(1, PDF_SPACE_SMALL_PT))
        return

    if has_table and table_rows_full:
        full_table = table_with_bars(
            table_title,
            table_rows_full,
            full_table_ratios,
            total_width_in=w_content,
        )
        story.append(full_table)
        if append_space_after_table_only:
            story.append(Spacer(1, PDF_SPACE_SMALL_PT))
        return

    if map_image_bytes:
        map_h = map_height_in_for_width(map_width_in)
        story.append(figure_from_bytes(map_image_bytes, width_in=map_width_in, height_in=map_h))
        story.append(Spacer(1, PDF_SPACE_MEDIUM_PT))
