"""HTTP analytics section for PDF reports."""

from __future__ import annotations

from datetime import date
from typing import Any

from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

from cloudflare_executive_report.pdf.layout_spec import HttpStreamLayout
from cloudflare_executive_report.pdf.maps import (
    map_height_in_for_width,
    world_map_from_country_totals_bytes,
)
from cloudflare_executive_report.pdf.primitives import (
    figure_from_bytes,
    make_styles,
    ranked_rows_from_dicts,
    table_with_bars,
)
from cloudflare_executive_report.pdf.stream_fragments import (
    append_missing_dates_note,
    append_stream_header,
    append_timeseries_if_enabled,
)
from cloudflare_executive_report.pdf.theme import Theme


def _country_totals_from_rollup(http: dict[str, Any]) -> dict[str, int]:
    out: dict[str, int] = {}
    for row in http.get("top_countries") or []:
        if not isinstance(row, dict):
            continue
        code = str(row.get("code") or "").upper()
        if len(code) != 2:
            continue
        out[code] = out.get(code, 0) + int(row.get("requests") or 0)
    return out


def append_http_stream(
    story: list[Any],
    *,
    zone_name: str,
    period_start: str,
    period_end: str,
    http: dict[str, Any],
    daily_requests: list[tuple[date, int | None]],
    missing_dates: list[str],
    layout: HttpStreamLayout,
    theme: Theme,
    top: int,
) -> None:
    styles = make_styles(theme)
    w_content = theme.content_width_in()

    blocks = set(layout.blocks)

    append_stream_header(
        story,
        styles,
        theme,
        blocks,
        stream_heading="HTTP",
        subtitle_lead="HTTP traffic for",
        zone_name=zone_name,
        period_start=period_start,
        period_end=period_end,
    )
    append_missing_dates_note(story, styles, blocks, missing_dates)

    req_h = str(http.get("total_requests_human") or "0")
    bw_h = str(http.get("total_bandwidth_human") or "0")
    ch = float(http.get("cache_hit_ratio") or 0.0)
    uv = str(http.get("unique_visitors_human") or "0")
    pv = str(http.get("page_views_human") or "0")

    if "kpi" in blocks:
        w_full = w_content * inch
        cell_w = w_full / 2 - 8
        kpi_data = [
            [
                Table(
                    [
                        [Paragraph("Total requests", styles["RepKpiLabel"])],
                        [Paragraph(req_h, styles["RepKpiValue"])],
                    ],
                    colWidths=[cell_w],
                ),
                Table(
                    [
                        [Paragraph("Bandwidth", styles["RepKpiLabel"])],
                        [Paragraph(bw_h, styles["RepKpiValue"])],
                    ],
                    colWidths=[cell_w],
                ),
            ],
            [
                Table(
                    [
                        [Paragraph("Cache hit ratio", styles["RepKpiLabel"])],
                        [Paragraph(f"{ch:.1f}%", styles["RepKpiValue"])],
                    ],
                    colWidths=[cell_w],
                ),
                Table(
                    [
                        [Paragraph("Unique visitors", styles["RepKpiLabel"])],
                        [Paragraph(uv, styles["RepKpiValue"])],
                    ],
                    colWidths=[cell_w],
                ),
            ],
        ]
        kpi = Table(kpi_data, colWidths=[w_full / 2, w_full / 2])
        kpi.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(theme.row_alt)),
                    ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor(theme.border)),
                    ("LINEBELOW", (0, 0), (-1, -1), 1.5, colors.HexColor(theme.primary)),
                    ("LEFTPADDING", (0, 0), (-1, -1), 14),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 14),
                    ("TOPPADDING", (0, 0), (-1, -1), 12),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
                ]
            )
        )
        story.append(kpi)
        story.append(
            Paragraph(
                f"<font color='{theme.muted}' size='8'>Page views: {pv}</font>",
                styles["RepFootnote"],
            )
        )
        story.append(Spacer(1, 18))

    country_totals = _country_totals_from_rollup(http)
    map_w = w_content
    map_h = map_height_in_for_width(map_w)

    if "map" in blocks:
        story.append(Paragraph("Requests by country", styles["RepSectionTight"]))
        map_png = world_map_from_country_totals_bytes(country_totals, theme=theme, width_in=map_w)
        story.append(figure_from_bytes(map_png, width_in=map_w, height_in=map_h))
        story.append(Spacer(1, 10))

    if "countries" in blocks:
        rows_raw = list(http.get("top_countries") or [])
        ranked: list[dict[str, Any]] = []
        for r in rows_raw[:top]:
            if not isinstance(r, dict):
                continue
            ranked.append(
                {
                    "name": str(r.get("country") or r.get("code") or ""),
                    "count": int(r.get("requests") or 0),
                    "percentage": float(r.get("percentage") or 0.0),
                }
            )
        bar_rows = ranked_rows_from_dicts(ranked, top, "name")
        if bar_rows:
            tbl = table_with_bars(
                "Top countries",
                bar_rows,
                styles,
                ratios=(0.42, 0.18, 0.40),
                total_width_in=w_content,
                theme=theme,
            )
            story.append(tbl)

    append_timeseries_if_enabled(
        story,
        styles,
        theme,
        blocks,
        daily_requests,
        chart_title="HTTP requests over period",
        y_axis_label="Requests",
    )
