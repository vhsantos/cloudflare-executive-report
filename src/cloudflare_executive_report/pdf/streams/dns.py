"""DNS analytics section for PDF reports."""

from __future__ import annotations

from datetime import date
from typing import Any

from reportlab.platypus import Spacer

from cloudflare_executive_report.common.constants import (
    PDF_MAP_SIDE_TABLE_MAX_ROWS,
    PDF_SPACE_SMALL_PT,
)
from cloudflare_executive_report.pdf.layout_spec import DnsStreamLayout
from cloudflare_executive_report.pdf.maps import world_map_from_colos_bytes
from cloudflare_executive_report.pdf.primitives import (
    flex_row_section,
    get_render_context,
    kpi_row,
    ranked_rows_from_dicts,
)
from cloudflare_executive_report.pdf.stream_fragments import (
    append_map_and_ranked_table,
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
    styles = get_render_context().styles
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
            kpi_row(
                [
                    ("Total queries", str(total_q) if total_q < 1000 else f"{total_q:,}"),
                    ("Avg queries/sec", f"{avg_qps:.3f}"),
                ]
            )
        )
        story.append(Spacer(1, PDF_SPACE_SMALL_PT))

    top_colos = list(dns.get("top_data_centers") or [])
    side_row_limit = min(top, PDF_MAP_SIDE_TABLE_MAX_ROWS)
    colo_rows_side = ranked_rows_from_dicts(top_colos, side_row_limit, "colo")
    colo_rows_full = ranked_rows_from_dicts(top_colos, top, "colo")
    append_map_and_ranked_table(
        story,
        styles,
        theme,
        blocks,
        map_block_name="map",
        table_block_name="colo_table",
        table_rows_side=colo_rows_side,
        table_rows_full=colo_rows_full,
        table_title="Top queries",
        side_table_ratios=(0.28, 0.26, 0.46),
        full_table_ratios=(0.28, 0.26, 0.46),
        build_map_png_for_width=lambda map_width_in: world_map_from_colos_bytes(
            top_colos[:top],
            theme=theme,
            width_in=map_width_in,
        ),
        append_space_after_table_only=True,
    )

    qnames = ranked_rows_from_dicts(list(dns.get("top_query_names") or []), top, "name")
    rtypes = ranked_rows_from_dicts(list(dns.get("top_record_types") or []), top, "type")
    rcodes = ranked_rows_from_dicts(list(dns.get("response_codes") or []), top, "code")

    qname_tables: list[tuple[str, list[list[Any]], tuple[float, float, float]]] = []
    if "qnames_rtypes" in blocks:
        qname_tables.append(("Top query names", qnames, (0.52, 0.18, 0.30)))
        qname_tables.append(("Top record types", rtypes, (0.28, 0.18, 0.54)))
    flex_row_section(story, qname_tables)

    proto = ranked_rows_from_dicts(list(dns.get("protocols") or []), top, "protocol")
    ip_v = ranked_rows_from_dicts(list(dns.get("ip_versions") or []), top, "version")

    dns_detail_tables: list[tuple[str, list[list[Any]], tuple[float, float, float]]] = []
    dns_triple_ratios = (0.52, 0.22, 0.26)
    if "rcode_proto" in blocks:
        dns_detail_tables.extend(
            [
                ("Response codes", rcodes, dns_triple_ratios),
                ("Protocols", proto, dns_triple_ratios),
                ("IP versions", ip_v, dns_triple_ratios),
            ]
        )
    elif "ip_versions" in blocks and ip_v:
        dns_detail_tables.append(("IP versions", ip_v, (0.22, 0.12, 0.66)))
    flex_row_section(story, dns_detail_tables)

    append_timeseries_if_enabled(
        story,
        styles,
        theme,
        blocks,
        daily_queries,
        chart_title="DNS queries",
        y_axis_label="Queries",
        heading=None,
    )
