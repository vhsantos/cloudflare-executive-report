"""Security analytics section for PDF reports (HTTP adaptive groups + sampled KPIs)."""

from __future__ import annotations

from datetime import date
from typing import Any

from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, Spacer, Table

from cloudflare_executive_report.common.constants import (
    PDF_SPACE_LARGE_PT,
    PDF_SPACE_MEDIUM_PT,
    PDF_SPACE_SMALL_PT,
)
from cloudflare_executive_report.common.formatting import format_count_human
from cloudflare_executive_report.pdf.charts import prepare_triple_line_daily_metric_series
from cloudflare_executive_report.pdf.layout_spec import SecurityStreamLayout
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
    format_security_action_label,
    format_security_source_label,
)
from cloudflare_executive_report.pdf.stream_fragments import (
    append_missing_dates_note,
    append_png_chart_section,
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
    w_half = w_full / 2
    half_inner = theme.half_inner_width_in()

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
        story.append(Spacer(1, PDF_SPACE_LARGE_PT))

    if "timeseries" in blocks:
        png_t, sub_t = prepare_triple_line_daily_metric_series(
            daily_security_triple,
            theme,
            chart_title="Daily requests",
            legend_mit="Mitigated",
            legend_cf="Served by Cloudflare",
            legend_or="Served by origin",
        )
        append_png_chart_section(
            story,
            styles,
            theme,
            blocks,
            heading=None,
            png=png_t,
            subtitle=sub_t,
        )

    sec_ratios = (0.40, 0.18, 0.42)

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

    if "actions" in blocks and "services" in blocks and (rows_top or svc_rows):
        left = (
            table_with_bars(
                "Security services",
                svc_rows,
                styles,
                ratios=sec_ratios,
                total_width_in=half_inner,
                theme=theme,
            )
            if svc_rows
            else Spacer(1, PDF_SPACE_SMALL_PT)
        )
        right = (
            table_with_bars(
                "Security actions",
                rows_top,
                styles,
                ratios=sec_ratios,
                total_width_in=half_inner,
                theme=theme,
            )
            if rows_top
            else Spacer(1, PDF_SPACE_SMALL_PT)
        )
        two_col = Table([[left, right]], colWidths=[w_half, w_half])
        two_col.setStyle(two_column_gap_style(theme))
        story.append(two_col)
        story.append(Spacer(1, PDF_SPACE_LARGE_PT))
    else:
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
            story.append(Spacer(1, PDF_SPACE_LARGE_PT))
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
            story.append(Spacer(1, PDF_SPACE_LARGE_PT))

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
        story.append(Spacer(1, PDF_SPACE_LARGE_PT))

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
            story.append(Spacer(1, PDF_SPACE_LARGE_PT))

    if "countries" in blocks:
        c_rows = ranked_rows_from_dicts(
            list(security.get("top_source_countries") or []),
            top,
            "country",
            value_key="requests",
        )
        if c_rows:
            story.append(
                table_with_bars(
                    "Top attacker countries",
                    c_rows,
                    styles,
                    ratios=(0.42, 0.18, 0.40),
                    total_width_in=w_content,
                    theme=theme,
                )
            )
            story.append(Spacer(1, PDF_SPACE_LARGE_PT))

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
    method_rows = ranked_rows_from_dicts(
        list(security.get("http_methods_breakdown") or []), top, "method"
    )

    if show_cache_perf and "methods" in blocks and (cache_rows or method_rows):
        left = (
            table_with_bars(
                "Cache performance",
                cache_rows,
                styles,
                ratios=sec_ratios,
                total_width_in=half_inner,
                theme=theme,
            )
            if cache_rows
            else Spacer(1, PDF_SPACE_SMALL_PT)
        )
        right = (
            table_with_bars(
                "HTTP methods",
                method_rows,
                styles,
                ratios=(0.28, 0.18, 0.54),
                total_width_in=half_inner,
                theme=theme,
            )
            if method_rows
            else Spacer(1, PDF_SPACE_SMALL_PT)
        )
        two_col = Table([[left, right]], colWidths=[w_half, w_half])
        two_col.setStyle(two_column_gap_style(theme))
        story.append(two_col)
        story.append(Spacer(1, PDF_SPACE_LARGE_PT))
    else:
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
            story.append(Spacer(1, PDF_SPACE_LARGE_PT))
        if "methods" in blocks and method_rows:
            story.append(
                table_with_bars(
                    "HTTP methods",
                    method_rows,
                    styles,
                    ratios=(0.28, 0.18, 0.54),
                    total_width_in=w_content,
                    theme=theme,
                )
            )
