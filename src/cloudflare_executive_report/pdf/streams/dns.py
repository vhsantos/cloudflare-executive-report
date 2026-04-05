"""DNS analytics section for PDF reports."""

from __future__ import annotations

from datetime import date
from typing import Any

from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

from cloudflare_executive_report.pdf.layout_spec import DnsStreamLayout
from cloudflare_executive_report.pdf.maps import map_height_in_for_width, world_map_from_colos_bytes
from cloudflare_executive_report.pdf.primitives import (
    colo_table_wrap,
    figure_from_bytes,
    kpi_two_cell_row,
    make_styles,
    ranked_rows_from_dicts,
    table_with_bars,
    two_column_gap_style,
)
from cloudflare_executive_report.pdf.stream_fragments import (
    append_missing_dates_note,
    append_stream_header,
    append_timeseries_if_enabled,
)
from cloudflare_executive_report.pdf.theme import Theme


def append_dns_stream(
    story: list[Any],
    *,
    zone_name: str,
    period_start: str,
    period_end: str,
    dns: dict[str, Any],
    daily_queries: list[tuple[date, int | None]],
    missing_dates: list[str],
    layout: DnsStreamLayout,
    theme: Theme,
    top: int,
) -> None:
    styles = make_styles(theme)
    w_content = theme.content_width_in()
    w_full = w_content * inch
    w_half = w_full / 2
    half_inner = theme.half_inner_width_in()
    third_inner = theme.third_inner_width_in()
    gap_pt = theme.col_gap_in * inch
    w_cell_triple = third_inner * inch

    blocks = set(layout.blocks)

    append_stream_header(
        story,
        styles,
        theme,
        blocks,
        stream_title="DNS queries",
        zone_name=zone_name,
        period_start=period_start,
        period_end=period_end,
    )
    append_missing_dates_note(story, styles, blocks, missing_dates)

    total_q = int(dns.get("total_queries", 0))
    avg_qps = float(dns.get("average_qps", 0.0))

    if "kpi" in blocks:
        story.append(
            kpi_two_cell_row(
                "Total queries",
                str(total_q) if total_q < 1000 else f"{total_q:,}",
                "Avg queries/sec",
                f"{avg_qps:.3f}",
                styles,
                theme=theme,
                content_width_in=w_content,
            )
        )
        story.append(Spacer(1, 18))

    top_colos = list(dns.get("top_data_centers") or [])
    map_w = w_content
    map_h = map_height_in_for_width(map_w)

    if "map" in blocks:
        story.append(Paragraph("Queries by country", styles["RepSectionTight"]))
        map_png = world_map_from_colos_bytes(top_colos[:top], theme=theme, width_in=map_w)
        story.append(figure_from_bytes(map_png, width_in=map_w, height_in=map_h))
        story.append(Spacer(1, 10))

    if "colo_table" in blocks:
        colo_rows = ranked_rows_from_dicts(top_colos, top, "colo")
        story.append(
            colo_table_wrap(colo_rows, total_width_in=w_content, theme=theme, styles=styles)
        )
        story.append(Spacer(1, 18))

    qnames = ranked_rows_from_dicts(list(dns.get("top_query_names") or []), top, "name")
    rtypes = ranked_rows_from_dicts(list(dns.get("top_record_types") or []), top, "type")
    rcodes = ranked_rows_from_dicts(list(dns.get("response_codes") or []), top, "code")

    if "qnames_rtypes" in blocks:
        left = table_with_bars(
            "Top query names",
            qnames,
            styles,
            ratios=(0.52, 0.18, 0.30),
            total_width_in=half_inner,
            theme=theme,
        )
        right = table_with_bars(
            "Top record types",
            rtypes,
            styles,
            ratios=(0.28, 0.18, 0.54),
            total_width_in=half_inner,
            theme=theme,
        )
        two_col = Table([[left, right]], colWidths=[w_half, w_half])
        two_col.setStyle(two_column_gap_style(theme))
        story.append(two_col)
        story.append(Spacer(1, 16))

    proto = ranked_rows_from_dicts(list(dns.get("protocols") or []), top, "protocol")
    ip_v = ranked_rows_from_dicts(list(dns.get("ip_versions") or []), top, "version")

    if "rcode_proto" in blocks:
        # Card width = column width; spacer columns for gutters (matches page content width).
        dns_triple_ratios = (0.52, 0.22, 0.26)
        col_codes = table_with_bars(
            "Response codes",
            rcodes,
            styles,
            ratios=dns_triple_ratios,
            total_width_in=third_inner,
            theme=theme,
        )
        col_proto = table_with_bars(
            "Protocols",
            proto,
            styles,
            ratios=dns_triple_ratios,
            total_width_in=third_inner,
            theme=theme,
        )
        col_ip = table_with_bars(
            "IP versions",
            ip_v,
            styles,
            ratios=dns_triple_ratios,
            total_width_in=third_inner,
            theme=theme,
        )
        gutter = Spacer(gap_pt, 1)
        triple = Table(
            [[col_codes, gutter, col_proto, gutter, col_ip]],
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
        story.append(Spacer(1, 16))
    elif "ip_versions" in blocks:
        ip_block = table_with_bars(
            "IP versions",
            ip_v,
            styles,
            ratios=(0.22, 0.12, 0.66),
            total_width_in=w_content,
            theme=theme,
        )
        story.append(ip_block)

    append_timeseries_if_enabled(
        story,
        styles,
        theme,
        blocks,
        daily_queries,
        chart_title="DNS queries over period",
        y_axis_label="Queries",
    )
