"""Cache analytics section for PDF reports."""

from __future__ import annotations

from datetime import date
from typing import Any

from reportlab.lib.units import inch
from reportlab.platypus import Spacer, Table, TableStyle

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
    kpi_multi_cell_row,
    make_styles,
    ranked_rows_from_dicts,
    table_with_bars,
    two_column_gap_style,
)
from cloudflare_executive_report.pdf.security_display import (
    apply_row_label_formatter,
    format_cache_status_label,
)
from cloudflare_executive_report.pdf.stream_fragments import (
    append_chart_section,
    append_missing_dates_note,
    append_stream_header,
)
from cloudflare_executive_report.pdf.theme import Theme


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


def _cache_ranked_cell(
    title: str,
    rows: list[list[Any]],
    *,
    styles: Any,
    theme: Theme,
    ratios: tuple[float, float, float],
    width_in: float,
) -> Any:
    if not rows:
        return Spacer(1, PDF_SPACE_SMALL_PT)
    return table_with_bars(title, rows, styles, ratios=ratios, total_width_in=width_in, theme=theme)


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
    styles = make_styles(theme)
    w_content = theme.content_width_in()
    w_full = w_content * 72.0
    w_half = w_full / 2
    half_inner = theme.half_inner_width_in()
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
            kpi_multi_cell_row(
                [
                    ("Total requests", tr),
                    ("Served by Cloudflare", scf),
                    ("Served by origin", sor),
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
                    ("Cache hit ratio", f"{hr:.1f}%"),
                ],
                styles,
                theme=theme,
                content_width_in=w_content,
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
        append_chart_section(
            story,
            styles,
            theme,
            blocks,
            heading=None,
            chart_bytes=chart_bytes_timeseries,
            subtitle=sub_t,
        )

    pair_ratios = (0.42, 0.18, 0.40)
    mime_full_ratios = (0.40, 0.18, 0.42)
    triple_ratios = (0.52, 0.22, 0.26)
    third_inner = theme.third_inner_width_in()
    gap_pt = theme.col_gap_in * inch
    w_cell_triple = third_inner * inch

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

    if "status" in blocks and "mime_http_1d" in blocks:
        gutter = Spacer(gap_pt, 1)
        triple = Table(
            [
                [
                    _cache_ranked_cell(
                        "Cache status Edge",
                        edge_rows,
                        styles=styles,
                        theme=theme,
                        ratios=triple_ratios,
                        width_in=third_inner,
                    ),
                    gutter,
                    _cache_ranked_cell(
                        "Cache status origin",
                        origin_rows,
                        styles=styles,
                        theme=theme,
                        ratios=triple_ratios,
                        width_in=third_inner,
                    ),
                    gutter,
                    _cache_ranked_cell(
                        "Traffic by response type",
                        mime_rows_triple,
                        styles=styles,
                        theme=theme,
                        ratios=triple_ratios,
                        width_in=third_inner,
                    ),
                ]
            ],
            colWidths=[w_cell_triple, gap_pt, w_cell_triple, gap_pt, w_cell_triple],
        )
        triple.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ]
            )
        )
        story.append(triple)
        story.append(Spacer(1, PDF_SPACE_SMALL_PT))
    elif "status" in blocks:
        pair = Table(
            [
                [
                    _cache_ranked_cell(
                        "Cache status Edge",
                        edge_rows,
                        styles=styles,
                        theme=theme,
                        ratios=pair_ratios,
                        width_in=half_inner,
                    ),
                    _cache_ranked_cell(
                        "Cache status origin",
                        origin_rows,
                        styles=styles,
                        theme=theme,
                        ratios=pair_ratios,
                        width_in=half_inner,
                    ),
                ]
            ],
            colWidths=[w_half, w_half],
        )
        pair.setStyle(two_column_gap_style(theme))
        story.append(pair)
        story.append(Spacer(1, PDF_SPACE_SMALL_PT))
    elif "mime_http_1d" in blocks:
        mime_rows_full = (
            ranked_rows_from_dicts(mime_rows_in, top, "content_type") if mime_rows_in else []
        )
        if mime_rows_full:
            story.append(
                table_with_bars(
                    "Traffic by response type",
                    mime_rows_full,
                    styles,
                    ratios=mime_full_ratios,
                    total_width_in=w_content,
                    theme=theme,
                )
            )
            story.append(Spacer(1, PDF_SPACE_SMALL_PT))

    path_rows = ranked_rows_from_dicts(list(cache.get("top_paths") or []), top, "path")
    if "paths" in blocks and path_rows:
        story.append(
            table_with_bars(
                "Top paths",
                path_rows,
                styles,
                ratios=(0.52, 0.18, 0.30),
                total_width_in=w_content,
                theme=theme,
            )
        )
