"""HTTP analytics section for PDF reports."""

from __future__ import annotations

from datetime import date
from typing import Any

from reportlab.platypus import Spacer

from cloudflare_executive_report.common.constants import (
    PDF_MAP_SIDE_TABLE_MAX_ROWS,
    PDF_SPACE_MEDIUM_PT,
    PDF_SPACE_SMALL_PT,
)
from cloudflare_executive_report.pdf.charts import (
    prepare_dual_line_daily_series,
    prepare_single_line_daily_series,
)
from cloudflare_executive_report.pdf.layout_spec import HttpStreamLayout
from cloudflare_executive_report.pdf.maps import (
    world_map_from_country_totals_bytes,
)
from cloudflare_executive_report.pdf.primitives import (
    get_render_context,
    kpi_row,
    ranked_rows_from_dicts,
)
from cloudflare_executive_report.pdf.stream_fragments import (
    append_map_and_ranked_table,
    append_missing_dates_note,
    append_prepared_timeseries_chart,
    append_stream_header,
)
from cloudflare_executive_report.pdf.theme import Theme


def collect_http_appendix_notes(http: dict[str, Any], *, profile: str) -> list[str]:
    """Return appendix notes derived from HTTP metrics present in this stream."""
    notes: list[str] = []
    if profile not in {"executive", "detailed"}:
        return notes
    if "unique_visitors" in http:
        notes.append(
            "Unique visitors are deduplicated for the selected period; daily totals may not "
            "match dashboard windows that include partial current-day traffic."
        )
    if "cache_hit_ratio" in http:
        notes.append(
            "Cache hit ratio depends on workload profile (static vs dynamic/API) and should be "
            "compared as a trend for the same zone."
        )
    return notes


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
    cache_stream_in_report: bool = False,
) -> None:
    styles = get_render_context().styles
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
            kpi_row(
                [
                    ("Total requests", tr),
                    ("Strict hits", cr),
                    ("Non-hits", ur),
                    ("Cache hit ratio", f"{ch:.1f}%"),
                ],
            )
        )
        story.append(Spacer(1, PDF_SPACE_MEDIUM_PT))
        story.append(
            kpi_row(
                [
                    ("Total bandwidth", tb),
                    ("Cached bandwidth", cbw),
                    ("Uncached bandwidth", ubw),
                    ("SSL (HTTPS) requests", ssl),
                ],
            )
        )
        story.append(Spacer(1, PDF_SPACE_MEDIUM_PT))
        story.append(
            kpi_row(
                [
                    ("Uniques Visitors (sum)", uv),
                    ("Peak Uniques Visitors", uv_peak),
                    ("Page views", pv),
                ],
            )
        )
        story.append(Spacer(1, PDF_SPACE_SMALL_PT))

    country_totals = _country_totals_from_rollup(http)
    side_row_limit = min(top, PDF_MAP_SIDE_TABLE_MAX_ROWS)

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
    bar_rows_full = ranked_rows_from_dicts(ranked, top, "name")
    bar_rows_side = ranked_rows_from_dicts(ranked, side_row_limit, "name")
    append_map_and_ranked_table(
        story,
        styles,
        theme,
        blocks,
        map_block_name="map",
        table_block_name="countries",
        table_rows_side=bar_rows_side,
        table_rows_full=bar_rows_full,
        table_title="Top requests",
        side_table_ratios=(0.40, 0.16, 0.44),
        full_table_ratios=(0.42, 0.18, 0.40),
        build_map_image_for_width=lambda map_width_in: world_map_from_country_totals_bytes(
            country_totals,
            theme=theme,
            width_in=map_width_in,
        ),
    )

    if "timeseries" in blocks:
        chart_bytes_uniques, sub_u = prepare_single_line_daily_series(
            daily_uniques,
            theme,
            chart_title="Unique visitors",
            y_axis_label="Unique visitors",
        )
        append_prepared_timeseries_chart(story, styles, theme, blocks, chart_bytes_uniques, sub_u)

        if not cache_stream_in_report:
            req_pairs = _zip_cached_uncached_pairs(daily_requests_cached, daily_requests_uncached)
            chart_bytes_requests, sub_r = prepare_dual_line_daily_series(
                req_pairs,
                theme,
                chart_title="HTTP requests",
                legend_a="Strict hits",
                legend_b="Non-hits",
            )
            append_prepared_timeseries_chart(
                story, styles, theme, blocks, chart_bytes_requests, sub_r
            )

        bw_pairs = _zip_cached_uncached_pairs(daily_bytes_cached, daily_bytes_uncached)
        chart_bytes_bandwidth, sub_b = prepare_dual_line_daily_series(
            bw_pairs,
            theme,
            chart_title="HTTP bandwidth",
            legend_a="Strict hits",
            legend_b="Non-hits",
        )
        append_prepared_timeseries_chart(story, styles, theme, blocks, chart_bytes_bandwidth, sub_b)
