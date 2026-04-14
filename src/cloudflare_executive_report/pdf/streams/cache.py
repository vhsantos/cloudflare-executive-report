"""Cache analytics section for PDF reports."""

from __future__ import annotations

from datetime import date
from typing import Any

from reportlab.platypus import Spacer

from cloudflare_executive_report.common.aggregation_helpers import (
    CACHE_ORIGIN_FETCH_STATUSES,
    norm_cache_status,
)
from cloudflare_executive_report.common.constants import (
    PDF_SPACE_MEDIUM_PT,
    PDF_SPACE_SMALL_PT,
)
from cloudflare_executive_report.pdf.charts import prepare_dual_line_daily_metric_series
from cloudflare_executive_report.pdf.layout_spec import CacheStreamLayout
from cloudflare_executive_report.pdf.primitives import (
    flex_row,
    flex_row_section,
    get_render_context,
    kpi_row,
    ranked_rows_from_dicts,
)
from cloudflare_executive_report.pdf.security_display import (
    apply_row_label_formatter,
    format_cache_status_label,
)
from cloudflare_executive_report.pdf.stream_fragments import (
    append_missing_dates_note,
    append_prepared_timeseries_chart,
    append_stream_header,
)
from cloudflare_executive_report.pdf.theme import Theme


def collect_cache_appendix_notes(cache: dict[str, Any], *, profile: str) -> list[str]:
    """Return appendix notes derived from cache metrics present in this stream."""
    notes: list[str] = []
    if profile not in {"executive", "detailed"}:
        return notes
    if "cache_hit_ratio" in cache:
        notes.append(
            "Cache hit ratio depends on workload profile (static vs dynamic/API) and should be "
            "compared as a trend for the same zone."
        )
    return notes


def _edge_and_origin_status_items(
    cache: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return Edge and Origin cache status rows.

    Prefer split keys, else derive from ``by_cache_status``.
    """
    edge = cache.get("by_cache_status_edge")
    origin = cache.get("by_cache_status_origin")
    if isinstance(edge, list) and isinstance(origin, list):
        return [r for r in edge if isinstance(r, dict)], [r for r in origin if isinstance(r, dict)]

    edge_out: list[dict[str, Any]] = []
    origin_out: list[dict[str, Any]] = []
    for row in cache.get("by_cache_status") or []:
        if not isinstance(row, dict):
            continue
        key = norm_cache_status(str(row.get("status") or row.get("value") or ""))
        if not key:
            continue
        if key in CACHE_ORIGIN_FETCH_STATUSES:
            origin_out.append(row)
        else:
            edge_out.append(row)
    edge_out.sort(key=lambda r: -int(r.get("count") or 0))
    origin_out.sort(key=lambda r: -int(r.get("count") or 0))
    return edge_out[:5], origin_out[:3]


def append_cache_stream(
    story: list[Any],
    *,
    zone_name: str,
    period_start: str,
    period_end: str,
    cache: dict[str, Any],
    daily_cache_cf_origin: list[tuple[date, tuple[int | None, int | None]]],
    missing_dates: list[str],
    layout: CacheStreamLayout,
    theme: Theme,
    top: int,
    http_mime_1d: list[dict[str, Any]] | None = None,
) -> None:
    styles = get_render_context().styles
    blocks = set(layout.blocks)
    mime_rows_in = http_mime_1d if http_mime_1d is not None else []

    append_stream_header(
        story,
        styles,
        theme,
        blocks,
        stream_title="Cache",
        zone_name=zone_name,
        period_start=period_start,
        period_end=period_end,
    )
    append_missing_dates_note(story, styles, blocks, missing_dates)

    if "kpi" in blocks:
        tr = str(cache.get("total_requests_sampled_human") or "0")
        scf = str(cache.get("served_cf_count_human") or "-")
        sor = str(cache.get("served_origin_count_human") or "-")
        tb = str(cache.get("total_edge_response_bytes_human") or "0B")
        hr = float(cache.get("cache_hit_ratio") or 0.0)
        story.append(
            kpi_row(
                [
                    ("Total requests", tr),
                    ("Served by Cloudflare", scf),
                    ("Served by origin", sor),
                ],
            )
        )
        story.append(Spacer(1, PDF_SPACE_MEDIUM_PT))
        story.append(
            kpi_row(
                [
                    ("Total bandwidth", tb),
                    ("Cache hit ratio", f"{hr:.1f}%"),
                ],
            )
        )
        story.append(Spacer(1, PDF_SPACE_SMALL_PT))

    if "timeseries" in blocks:
        chart_bytes_timeseries, sub_t = prepare_dual_line_daily_metric_series(
            daily_cache_cf_origin,
            theme,
            chart_title="Cache requests",
            legend_a="Served by Cloudflare",
            legend_b="Served by origin",
        )
        append_prepared_timeseries_chart(
            story, styles, theme, blocks, chart_bytes_timeseries, sub_t
        )

    pair_ratios = (0.42, 0.18, 0.40)
    mime_full_ratios = (0.40, 0.18, 0.42)
    triple_ratios = (0.52, 0.22, 0.26)

    edge_items, origin_items = _edge_and_origin_status_items(cache)
    edge_rows = ranked_rows_from_dicts(
        apply_row_label_formatter(edge_items, 5, "status", format_cache_status_label),
        5,
        "status",
    )
    origin_rows = ranked_rows_from_dicts(
        apply_row_label_formatter(origin_items, 3, "status", format_cache_status_label),
        3,
        "status",
    )
    mime_rows_triple = (
        ranked_rows_from_dicts(mime_rows_in, 5, "content_type") if mime_rows_in else []
    )

    cache_ranked_tables: list[tuple[str, list[list[Any]], tuple[float, float, float]]] = []
    if "status" in blocks:
        status_ratios = triple_ratios if "mime_http_1d" in blocks else pair_ratios
        cache_ranked_tables.append(("Cache status Edge", edge_rows, status_ratios))
        cache_ranked_tables.append(("Cache status origin", origin_rows, status_ratios))
    if "mime_http_1d" in blocks:
        if "status" in blocks:
            cache_ranked_tables.append(
                ("Traffic by response type", mime_rows_triple, triple_ratios),
            )
        else:
            mime_rows_full = (
                ranked_rows_from_dicts(mime_rows_in, top, "content_type") if mime_rows_in else []
            )
            if mime_rows_full:
                cache_ranked_tables.append(
                    ("Traffic by response type", mime_rows_full, mime_full_ratios),
                )
    flex_row_section(story, cache_ranked_tables)

    path_rows = ranked_rows_from_dicts(list(cache.get("top_paths") or []), top, "path")
    if "paths" in blocks and path_rows:
        story.append(
            flex_row([("Top paths", path_rows, (0.52, 0.18, 0.30))]),
        )
