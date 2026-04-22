"""Security analytics section for PDF reports (HTTP adaptive groups + sampled KPIs)."""

from __future__ import annotations

from datetime import date
from typing import Any

from reportlab.platypus import Spacer

from cloudflare_executive_report.common.constants import (
    PDF_MAP_SIDE_TABLE_MAX_ROWS,
    PDF_SPACE_MEDIUM_PT,
    PDF_SPACE_SMALL_PT,
)
from cloudflare_executive_report.common.formatting import format_count_human
from cloudflare_executive_report.pdf.charts import prepare_triple_line_daily_series
from cloudflare_executive_report.pdf.layout_spec import SecurityStreamLayout
from cloudflare_executive_report.pdf.maps import world_map_from_country_totals_bytes
from cloudflare_executive_report.pdf.primitives import (
    flex_row_section,
    get_render_context,
    kpi_row,
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
    append_map_and_ranked_table,
    append_missing_dates_note,
    append_prepared_timeseries_chart,
    append_stream_header,
)
from cloudflare_executive_report.pdf.theme import Theme


def collect_security_appendix_notes(security: dict[str, Any], *, profile: str) -> list[str]:
    """Return appendix notes derived from security metrics and tables."""
    notes: list[str] = []
    if profile not in {"executive", "detailed"}:
        return notes
    if "mitigation_rate_pct" in security:
        notes.append(
            "Mitigation metrics reflect sampled events and configured actions; trend direction "
            "is more reliable than single-day absolute counts."
        )
    if profile == "detailed" and list(security.get("top_attack_sources") or []):
        notes.append(
            "Frequently seen attacker IPs are merged from daily top 10 lists; consistently "
            "active sources that never reach daily top 10 may not appear."
        )
    return notes


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
    styles = get_render_context().styles
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
            kpi_row(
                [
                    ("Traffic overview", tr),
                    ("Served by Cloudflare", scf),
                    ("Served by origin", sor),
                ]
            )
        )
        story.append(Spacer(1, PDF_SPACE_MEDIUM_PT))
        story.append(
            kpi_row(
                [
                    ("Mitigated", mit_display),
                    ("Challenges", ch),
                    ("Blocks", blk),
                ]
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
        build_map_image_for_width=lambda map_width_in: world_map_from_country_totals_bytes(
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

    breakdown_tables: list[tuple[str, list[list[Any]], tuple[float, float, float]]] = []
    if "methods" in blocks and method_rows:
        breakdown_tables.append(("HTTP methods", method_rows, method_ratios))
    if "services" in blocks and svc_rows:
        breakdown_tables.append(("Security services", svc_rows, sec_ratios))
    if "actions" in blocks and rows_top:
        breakdown_tables.append(("Security actions", rows_top, sec_ratios))
    flex_row_section(story, breakdown_tables)

    atk_items: list[dict[str, Any]] = []
    for r in security.get("top_attack_sources") or []:
        if not isinstance(r, dict):
            continue
        ip = str(r.get("ip") or "").strip()
        co = str(r.get("country") or "").strip()
        label = f"{ip} ({co})" if ip and co else ip or co or "-"
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

    attack_sources_enabled = "attack_sources" in blocks
    attack_paths_enabled = "attack_paths" in blocks
    rows_atk = ranked_rows_from_dicts(atk_items, top, "label")
    path_items = list(security.get("top_attack_paths") or [])
    path_rows = ranked_rows_from_dicts(path_items, top, "path")

    attack_tables: list[tuple[str, list[list[Any]], tuple[float, float, float]]] = []
    if attack_sources_enabled and rows_atk:
        attack_tables.append(
            ("Frequently seen attacker IPs", rows_atk, (0.52, 0.18, 0.30)),
        )
    if attack_paths_enabled and path_rows:
        attack_tables.append(("Top attacked paths", path_rows, (0.48, 0.18, 0.34)))
    flex_row_section(story, attack_tables)

    if "timeseries" in blocks:
        chart_bytes_timeseries, sub_t = prepare_triple_line_daily_series(
            daily_security_triple,
            theme,
            chart_title="Security traffic",
            legend_a="Served by Cloudflare",
            legend_b="Served by origin",
            legend_c="Mitigated",
        )
        append_prepared_timeseries_chart(
            story, styles, theme, blocks, chart_bytes_timeseries, sub_t
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
        story.append(table_with_bars("Cache performance", cache_rows, sec_ratios))
        story.append(Spacer(1, PDF_SPACE_SMALL_PT))
