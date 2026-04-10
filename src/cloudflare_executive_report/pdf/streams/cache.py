"""Cache analytics section for PDF reports."""

from __future__ import annotations

from datetime import date
from typing import Any

from reportlab.platypus import Paragraph, Spacer, Table

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

    cache_ratios = (0.42, 0.18, 0.40)
    mime_ratios = (0.40, 0.18, 0.42)

    status_rows = ranked_rows_from_dicts(
        apply_row_label_formatter(
            list(cache.get("by_cache_status") or []),
            top,
            "status",
            format_cache_status_label,
        ),
        top,
        "status",
    )
    # Keep side-by-side tables aligned: MIME rows follow cache-status row count.
    mime_top = len(status_rows) if status_rows else top
    mime_rows = (
        ranked_rows_from_dicts(mime_rows_in, mime_top, "content_type") if mime_rows_in else []
    )

    if "status" in blocks and "mime_http_1d" in blocks and (status_rows or mime_rows):
        left = (
            table_with_bars(
                "Cache status",
                status_rows,
                styles,
                ratios=cache_ratios,
                total_width_in=half_inner,
                theme=theme,
            )
            if status_rows
            else Spacer(1, PDF_SPACE_SMALL_PT)
        )
        right = (
            table_with_bars(
                "Traffic by edge response type",
                mime_rows,
                styles,
                ratios=mime_ratios,
                total_width_in=half_inner,
                theme=theme,
            )
            if mime_rows
            else Spacer(1, PDF_SPACE_SMALL_PT)
        )
        two_col = Table([[left, right]], colWidths=[w_half, w_half])
        two_col.setStyle(two_column_gap_style(theme))
        story.append(two_col)
        story.append(Spacer(1, PDF_SPACE_SMALL_PT))
    else:
        if "status" in blocks and status_rows:
            story.append(
                table_with_bars(
                    "Cache status",
                    status_rows,
                    styles,
                    ratios=cache_ratios,
                    total_width_in=w_content,
                    theme=theme,
                )
            )
            story.append(Spacer(1, PDF_SPACE_SMALL_PT))
        if "mime_http_1d" in blocks and mime_rows:
            story.append(
                table_with_bars(
                    "Traffic by edge response type",
                    mime_rows,
                    styles,
                    ratios=mime_ratios,
                    total_width_in=w_content,
                    theme=theme,
                )
            )
            story.append(Spacer(1, PDF_SPACE_SMALL_PT))
            story.append(
                Paragraph(
                    "<i>From cached <tt>http.json</tt> (httpRequests1dGroups "
                    "<tt>contentTypeMap</tt>).</i>",
                    styles["RepFootnote"],
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
