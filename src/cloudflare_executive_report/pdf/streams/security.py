"""Security analytics section for PDF reports (HTTP adaptive groups + sampled KPIs)."""

from __future__ import annotations

from datetime import date
from typing import Any

from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

from cloudflare_executive_report.common.constants import (
    PDF_MAP_SIDE_TABLE_MAX_ROWS,
    PDF_SPACE_MEDIUM_PT,
    PDF_SPACE_SMALL_PT,
)
from cloudflare_executive_report.common.formatting import format_count_human
from cloudflare_executive_report.pdf.charts import prepare_triple_line_daily_metric_series
from cloudflare_executive_report.pdf.layout_spec import SecurityStreamLayout
from cloudflare_executive_report.pdf.maps import world_map_from_country_totals_bytes
from cloudflare_executive_report.pdf.primitives import (
    kpi_multi_cell_row,
    make_styles,
    ranked_rows_from_dicts,
    table_with_bars,
)
from cloudflare_executive_report.pdf.security_display import (
    apply_row_label_formatter,
    format_cache_status_label,
    format_security_action_label,
    format_security_source_label,
)
from cloudflare_executive_report.pdf.stream_fragments import (
    append_chart_section,
    append_map_and_ranked_table,
    append_missing_dates_note,
    append_stream_header,
)
from cloudflare_executive_report.pdf.theme import Theme


def append_security_stream(
    story: list[Any],
    *,
    zone_name: str,
    period_start: str,
    period_end: str,
    security: dict[str, Any],
    daily_security_triple: list[tuple[date, tuple[int | None, int | None, int | None]]],
    missing_dates: list[str],
    layout: SecurityStreamLayout,
    theme: Theme,
    top: int,
    cache_stream_in_report: bool = False,
) -> None:
    styles = make_styles(theme)
    w_content = theme.content_width_in()
    w_full = w_content * inch
    w_third = w_full / 3
    third_inner = theme.third_inner_width_in()
    gap_pt = theme.col_gap_in * inch

    blocks = set(layout.blocks)
    # Same breakdown as the dedicated Cache page (from security aggregate); skip when both run.
    show_cache_perf = ("cache" in blocks) and not cache_stream_in_report

    append_stream_header(
        story,
        styles,
        theme,
        blocks,
        stream_title="Security",
        zone_name=zone_name,
        period_start=period_start,
        period_end=period_end,
    )
    append_missing_dates_note(story, styles, blocks, missing_dates)

    if "kpi" in blocks:
        tr = str(security.get("http_requests_sampled_human") or "-")
        mit = int(security.get("mitigated_count") or 0)
        mrate = float(security.get("mitigation_rate_pct") or 0.0)
        # Same field as ``build_security_section``; ``format_count_human`` if *_human missing.
        mit_h = str(security.get("mitigated_count_human") or format_count_human(mit))
        mit_display = f"{mit_h} ({mrate:.1f}%)" if mit else "0"
        scf = str(security.get("served_cf_count_human") or "-")
        sor = str(security.get("served_origin_count_human") or "-")
        ch = str(security.get("challenge_events_sampled_human") or "-")
        blk = str(security.get("block_events_sampled_human") or "-")

        story.append(
            kpi_multi_cell_row(
                [
                    ("Traffic overview", tr),
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
                    ("Mitigated", mit_display),
                    ("Challenges", ch),
                    ("Blocks", blk),
                ],
                styles,
                theme=theme,
                content_width_in=w_content,
            )
        )
        story.append(Spacer(1, PDF_SPACE_SMALL_PT))

    sec_ratios = (0.40, 0.18, 0.42)
    method_ratios = (0.28, 0.18, 0.54)

    country_items: list[dict[str, Any]] = []
    country_totals: dict[str, int] = {}
    for row in list(security.get("top_source_countries") or [])[:top]:
        if not isinstance(row, dict):
            continue
        country_name = str(row.get("country") or row.get("code") or "").strip()
        request_count = int(row.get("requests") or row.get("count") or 0)
        percentage = float(row.get("percentage") or 0.0)
        if country_name:
            country_items.append(
                {
                    "name": country_name,
                    "count": request_count,
                    "percentage": percentage,
                }
            )
        country_code = str(row.get("code") or "").upper().strip()
        if len(country_code) == 2 and request_count > 0:
            country_totals[country_code] = country_totals.get(country_code, 0) + request_count

    side_row_limit = min(top, PDF_MAP_SIDE_TABLE_MAX_ROWS)
    country_rows_side = ranked_rows_from_dicts(country_items, side_row_limit, "name")
    country_rows_full = ranked_rows_from_dicts(country_items, top, "name")
    append_map_and_ranked_table(
        story,
        styles,
        theme,
        blocks,
        map_block_name="countries",
        table_block_name="countries",
        table_rows_side=country_rows_side,
        table_rows_full=country_rows_full,
        table_title="Top attacker countries",
        side_table_ratios=(0.42, 0.18, 0.40),
        full_table_ratios=(0.42, 0.18, 0.40),
        build_map_png_for_width=lambda map_width_in: world_map_from_country_totals_bytes(
            country_totals,
            theme=theme,
            width_in=map_width_in,
        ),
    )

    rows_top = ranked_rows_from_dicts(
        apply_row_label_formatter(
            list(security.get("top_actions") or []),
            top,
            "action",
            format_security_action_label,
        ),
        top,
        "action",
    )
    svc_rows = ranked_rows_from_dicts(
        apply_row_label_formatter(
            list(security.get("top_security_services") or []),
            top,
            "service",
            format_security_source_label,
        ),
        top,
        "service",
    )
    method_rows = ranked_rows_from_dicts(
        list(security.get("http_methods_breakdown") or []), top, "method"
    )

    if (
        "services" in blocks
        and "methods" in blocks
        and "actions" in blocks
        and (svc_rows or method_rows or rows_top)
    ):
        col_methods = (
            table_with_bars(
                "HTTP methods",
                method_rows,
                styles,
                ratios=method_ratios,
                total_width_in=third_inner,
                theme=theme,
            )
            if method_rows
            else Spacer(1, PDF_SPACE_SMALL_PT)
        )
        col_services = (
            table_with_bars(
                "Security services",
                svc_rows,
                styles,
                ratios=sec_ratios,
                total_width_in=third_inner,
                theme=theme,
            )
            if svc_rows
            else Spacer(1, PDF_SPACE_SMALL_PT)
        )

        col_actions = (
            table_with_bars(
                "Security actions",
                rows_top,
                styles,
                ratios=sec_ratios,
                total_width_in=third_inner,
                theme=theme,
            )
            if rows_top
            else Spacer(1, PDF_SPACE_SMALL_PT)
        )
        gutter = Spacer(gap_pt, 1)
        triple = Table(
            [[col_methods, gutter, col_services, gutter, col_actions]],
            colWidths=[w_third, gap_pt, w_third, gap_pt, w_third],
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
    else:
        if "services" in blocks and svc_rows:
            story.append(
                table_with_bars(
                    "Security services",
                    svc_rows,
                    styles,
                    ratios=sec_ratios,
                    total_width_in=w_content,
                    theme=theme,
                )
            )
            story.append(Spacer(1, PDF_SPACE_SMALL_PT))
        if "methods" in blocks and method_rows:
            story.append(
                table_with_bars(
                    "HTTP methods",
                    method_rows,
                    styles,
                    ratios=method_ratios,
                    total_width_in=w_content,
                    theme=theme,
                )
            )
            story.append(Spacer(1, PDF_SPACE_SMALL_PT))
        if "actions" in blocks and rows_top:
            story.append(
                table_with_bars(
                    "Security actions",
                    rows_top,
                    styles,
                    ratios=sec_ratios,
                    total_width_in=w_content,
                    theme=theme,
                )
            )
            story.append(Spacer(1, PDF_SPACE_SMALL_PT))

    if "timeseries" in blocks:
        chart_bytes_timeseries, sub_t = prepare_triple_line_daily_metric_series(
            daily_security_triple,
            theme,
            chart_title="Daily requests",
            legend_mit="Mitigated",
            legend_cf="Served by Cloudflare",
            legend_or="Served by origin",
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
        story.append(Spacer(1, PDF_SPACE_SMALL_PT))

    atk_items: list[dict[str, Any]] = []
    for r in security.get("top_attack_sources") or []:
        if not isinstance(r, dict):
            continue
        ip = str(r.get("ip") or "").strip()
        co = str(r.get("country") or "").strip()
        if ip and co:
            label = f"{ip} ({co})"
        else:
            label = ip or co or "-"
        act = str(r.get("action") or "").strip()
        if act:
            label = f"{label} · {act}"
        atk_items.append(
            {
                "label": label,
                "count": int(r.get("count") or 0),
                "percentage": float(r.get("percentage") or 0.0),
            }
        )

    if "attack_sources" in blocks and atk_items:
        rows_atk = ranked_rows_from_dicts(atk_items, top, "label")
        story.append(
            table_with_bars(
                "Frequently seen attacker IPs (approximate - from daily top lists)",
                rows_atk,
                styles,
                ratios=(0.52, 0.18, 0.30),
                total_width_in=w_content,
                theme=theme,
            )
        )
        story.append(Spacer(1, PDF_SPACE_SMALL_PT))
        story.append(
            Paragraph(
                "<i>Note: For multi-day reports, IPs are merged from daily top 10 lists. "
                "IPs that attack consistently but never reach daily top 10 may not appear.</i>",
                styles["RepFootnote"],
            )
        )
        story.append(Spacer(1, PDF_SPACE_SMALL_PT))

    if "attack_paths" in blocks:
        path_items = list(security.get("top_attack_paths") or [])
        path_rows = ranked_rows_from_dicts(path_items, top, "path")
        if path_rows:
            story.append(
                table_with_bars(
                    "Top attacked paths",
                    path_rows,
                    styles,
                    ratios=(0.48, 0.18, 0.34),
                    total_width_in=w_content,
                    theme=theme,
                )
            )
            story.append(Spacer(1, PDF_SPACE_SMALL_PT))

    cache_rows = ranked_rows_from_dicts(
        apply_row_label_formatter(
            list(security.get("cache_status_breakdown") or []),
            top,
            "status",
            format_cache_status_label,
        ),
        top,
        "status",
    )
    if show_cache_perf and cache_rows:
        story.append(
            table_with_bars(
                "Cache performance",
                cache_rows,
                styles,
                ratios=sec_ratios,
                total_width_in=w_content,
                theme=theme,
            )
        )
        story.append(Spacer(1, PDF_SPACE_SMALL_PT))
