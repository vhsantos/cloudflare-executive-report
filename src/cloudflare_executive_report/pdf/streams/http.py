"""HTTP analytics section for PDF reports."""

from __future__ import annotations

from datetime import date
from typing import Any

from reportlab.platypus import Paragraph, Spacer

from cloudflare_executive_report.pdf.layout_spec import HttpStreamLayout
from cloudflare_executive_report.pdf.maps import (
    map_height_in_for_width,
    world_map_from_country_totals_bytes,
)
from cloudflare_executive_report.pdf.primitives import (
    figure_from_bytes,
    kpi_multi_cell_row,
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
        story.append(
            kpi_multi_cell_row(
                [
                    ("Total requests", req_h),
                    ("Bandwidth", bw_h),
                    ("Cache hit ratio", f"{ch:.1f}%"),
                    ("Unique visitors", uv),
                    ("Page views", pv),
                ],
                styles,
                theme=theme,
                content_width_in=w_content,
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
