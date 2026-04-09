"""HTTP analytics section for PDF reports."""

from __future__ import annotations

from datetime import date
from typing import Any

from reportlab.platypus import Paragraph, Spacer

from cloudflare_executive_report.common.constants import (
    PDF_SPACE_LARGE_PT,
    PDF_SPACE_MEDIUM_PT,
)
from cloudflare_executive_report.pdf.charts import (
    prepare_daily_metric_series,
    prepare_stacked_daily_metric_series,
)
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
    append_png_chart_section,
    append_stream_header,
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


def _zip_cached_uncached_pairs(
    cached: list[tuple[date, int | None]],
    uncached: list[tuple[date, int | None]],
) -> list[tuple[date, tuple[int | None, int | None]]]:
    return [(dc[0], (dc[1], du[1])) for dc, du in zip(cached, uncached, strict=True)]


def append_http_stream(
    story: list[Any],
    *,
    zone_name: str,
    period_start: str,
    period_end: str,
    http: dict[str, Any],
    daily_requests_cached: list[tuple[date, int | None]],
    daily_requests_uncached: list[tuple[date, int | None]],
    daily_bytes_cached: list[tuple[date, int | None]],
    daily_bytes_uncached: list[tuple[date, int | None]],
    daily_uniques: list[tuple[date, int | None]],
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
        stream_title="HTTP traffic",
        zone_name=zone_name,
        period_start=period_start,
        period_end=period_end,
    )
    append_missing_dates_note(story, styles, blocks, missing_dates)

    tr = str(http.get("total_requests_human") or "0")
    cr = str(http.get("cached_requests_human") or "0")
    ur = str(http.get("uncached_requests_human") or "0")
    ch = float(http.get("cache_hit_ratio") or 0.0)
    tb = str(http.get("total_bandwidth_human") or "0")
    cbw = str(http.get("cached_bandwidth_human") or "0")
    ubw = str(http.get("uncached_bandwidth_human") or "0")
    ssl = str(http.get("encrypted_requests_human") or "0")
    uv = str(http.get("unique_visitors_human") or "0")
    uv_peak = str(http.get("max_uniques_single_day_human") or "0")
    pv = str(http.get("page_views_human") or "0")
    if "kpi" in blocks:
        story.append(
            kpi_multi_cell_row(
                [
                    ("Total requests", tr),
                    ("Cached requests", cr),
                    ("Uncached requests", ur),
                    ("Cache hit ratio", f"{ch:.1f}%"),
                ],
                styles,
                theme=theme,
                content_width_in=w_content,
            )
        )
        story.append(Spacer(1, PDF_SPACE_MEDIUM_PT))
        story.append(
            kpi_multi_cell_row(
                [
                    ("Total bandwidth", tb),
                    ("Cached bandwidth", cbw),
                    ("Uncached bandwidth", ubw),
                    ("SSL (HTTPS) requests", ssl),
                ],
                styles,
                theme=theme,
                content_width_in=w_content,
            )
        )
        story.append(Spacer(1, PDF_SPACE_MEDIUM_PT))
        story.append(
            kpi_multi_cell_row(
                [
                    ("Uniques Visitors (sum)", uv),
                    ("Peak Uniques Visitors", uv_peak),
                    ("Page views", pv),
                ],
                styles,
                theme=theme,
                content_width_in=w_content,
            )
        )
        story.append(Spacer(1, PDF_SPACE_LARGE_PT))

    country_totals = _country_totals_from_rollup(http)
    map_w = w_content
    map_h = map_height_in_for_width(map_w)

    if "map" in blocks:
        story.append(Paragraph("Requests by country", styles["RepSectionTight"]))
        map_png = world_map_from_country_totals_bytes(country_totals, theme=theme, width_in=map_w)
        story.append(figure_from_bytes(map_png, width_in=map_w, height_in=map_h))
        story.append(Spacer(1, PDF_SPACE_MEDIUM_PT))

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

    if "timeseries" in blocks:
        req_pairs = _zip_cached_uncached_pairs(daily_requests_cached, daily_requests_uncached)
        png_r, sub_r = prepare_stacked_daily_metric_series(
            req_pairs,
            theme,
            chart_title="HTTP requests",
            bottom_legend="Cached",
            top_legend="Uncached",
        )
        append_png_chart_section(
            story,
            styles,
            theme,
            blocks,
            heading=None,
            png=png_r,
            subtitle=sub_r,
        )

        bw_pairs = _zip_cached_uncached_pairs(daily_bytes_cached, daily_bytes_uncached)
        png_b, sub_b = prepare_stacked_daily_metric_series(
            bw_pairs,
            theme,
            chart_title="HTTP bandwidth",
            bottom_legend="Cached",
            top_legend="Uncached",
            y_scale="bytes",
        )
        append_png_chart_section(
            story,
            styles,
            theme,
            blocks,
            heading=None,
            png=png_b,
            subtitle=sub_b,
        )

        png_u, sub_u = prepare_daily_metric_series(
            daily_uniques,
            theme,
            chart_title="Unique visitors",
            y_axis_label="Unique visitors",
        )
        append_png_chart_section(
            story,
            styles,
            theme,
            blocks,
            heading=None,
            png=png_u,
            subtitle=sub_u,
        )
