"""Email Routing and Security analytics page for the PDF report."""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from reportlab.platypus import Spacer

from cloudflare_executive_report.common.constants import PDF_SPACE_MEDIUM_PT
from cloudflare_executive_report.pdf.charts import prepare_triple_line_daily_series
from cloudflare_executive_report.pdf.layout_spec import EmailStreamLayout
from cloudflare_executive_report.pdf.primitives import (
    get_render_context,
    kpi_row,
    table_standard_card,
)
from cloudflare_executive_report.pdf.stream_fragments import (
    append_chart_section,
    append_missing_dates_note,
    append_stream_header,
)
from cloudflare_executive_report.pdf.theme import Theme


def collect_email_appendix_notes(email: dict[str, Any], *, profile: str) -> list[str]:
    """Return appendix notes derived from Email metrics present in this stream."""
    notes: list[str] = []
    if profile not in {"executive", "detailed"}:
        return notes
    if email.get("total_received", 0) > 0:
        notes.append(
            "Email routing metrics are derived from Adaptive Groups and may be subject to "
            "eventual consistency or slight sampling in some views."
        )
    if email.get("dns_dmarc_policy") == "unavailable":
        notes.append(
            "DMARC/SPF/DKIM status is checked via live DNS TXT records for the zone apex; "
            "results may vary if records were changed during the reporting period."
        )
    return notes


def append_email_stream(
    story: list[Any],
    *,
    zone_name: str,
    period_start: str,
    period_end: str,
    email: dict[str, Any],
    daily_forwarded: list[tuple[date, int | None]],
    daily_delivery_failed: list[tuple[date, int | None]],
    daily_dropped_rejected: list[tuple[date, int | None]],
    missing_dates: list[str],
    layout: EmailStreamLayout,
    theme: Theme,
) -> None:
    """Append the Email stream page to the report story."""
    styles = get_render_context().styles
    blocks = set(layout.blocks)

    append_stream_header(
        story,
        styles,
        theme,
        blocks,
        stream_title="Email",
        zone_name=zone_name,
        period_start=period_start,
        period_end=period_end,
    )
    append_missing_dates_note(story, styles, blocks, missing_dates)

    # If Email Routing is disabled, only show DNS-based KPIs and exit
    if not email.get("email_routing_enabled"):
        if "kpi" in blocks:
            story.append(
                kpi_row(
                    [
                        ("DMARC Policy", str(email.get("dns_dmarc_policy") or "N/A")),
                        ("SPF Policy", str(email.get("dns_spf_policy") or "N/A")),
                        ("DKIM in Use", "yes" if email.get("dns_dkim_configured") else "no"),
                    ]
                )
            )
        return  # Exit early - nothing else to show

    # If we get here, Email Routing is enabled - show full page
    if "kpi" in blocks:
        # Row 1: Security Posture
        story.append(
            kpi_row(
                [
                    ("DMARC Policy", str(email.get("dns_dmarc_policy") or "N/A")),
                    ("SPF Policy", str(email.get("dns_spf_policy") or "N/A")),
                    ("DKIM in Use", "yes" if email.get("dns_dkim_configured") else "no"),
                    ("Routing Rules", str(email.get("routing_rules_count") or 0)),
                ]
            )
        )
        story.append(Spacer(1, PDF_SPACE_MEDIUM_PT))

        # Row 2: Alignment Rates
        dmarc_rate = email.get("dmarc_pass_rate_pct", 0)
        spf_rate = email.get("spf_aligned_rate_pct", 0)
        dkim_rate = email.get("dkim_aligned_rate_pct", 0)

        logging.debug(
            "Rendering Email Alignment for %s: DMARC=%.1f%%, SPF=%.1f%%, DKIM=%.1f%%",
            zone_name,
            dmarc_rate,
            spf_rate,
            dkim_rate,
        )

        story.append(
            kpi_row(
                [
                    ("DMARC Pass", f"{dmarc_rate:.1f}%"),
                    ("SPF Aligned", f"{spf_rate:.1f}%"),
                    ("DKIM Aligned", f"{dkim_rate:.1f}%"),
                ]
            )
        )

        # Row 3: Routing Volume (Only if enabled)
        story.append(Spacer(1, PDF_SPACE_MEDIUM_PT))
        story.append(
            kpi_row(
                [
                    ("Total Received", email.get("total_received_human", "0")),
                    ("Forwarded", email.get("forwarded_human", "0")),
                    ("Delivery Failed", email.get("delivery_failed_human", "0")),
                    ("Dropped", email.get("dropped_human", "0")),
                    ("Rejected", email.get("rejected_human", "0")),
                ]
            )
        )

    if "timeseries" in blocks:
        story.append(Spacer(1, PDF_SPACE_MEDIUM_PT))
        # Combine daily lists for triple line chart
        triples: list[tuple[date, tuple[int | None, int | None, int | None]]] = []
        for i in range(len(daily_forwarded)):
            d, fwd = daily_forwarded[i]
            _, fail = daily_delivery_failed[i]
            _, dr = daily_dropped_rejected[i]
            triples.append((d, (fwd, fail, dr)))

        chart_bytes, sub = prepare_triple_line_daily_series(
            triples,
            theme,
            chart_title="Email Routing Activity",
            legend_a="Forwarded",
            legend_b="Delivery Failed",
            legend_c="Dropped/Rejected",
        )
        append_chart_section(
            story,
            styles,
            theme,
            blocks,
            heading=None,
            chart_bytes=chart_bytes,
            subtitle=sub,
        )

    if "top_sources" in blocks:
        story.append(Spacer(1, PDF_SPACE_MEDIUM_PT))
        rows = [["Source", "Volume", "DMARC Pass", "SPF Aligned", "DKIM Aligned"]]
        for s in email.get("top_sources") or []:
            rows.append(
                [
                    str(s.get("sourceOrgName") or "-"),
                    str(s.get("volume_human") or "0"),
                    f"{s.get('dmarc_pass_pct', 0):.1f}%",
                    f"{s.get('spf_aligned_pct', 0):.1f}%",
                    f"{s.get('dkim_aligned_pct', 0):.1f}%",
                ]
            )

        if len(rows) > 1:
            story.append(
                table_standard_card(
                    "Top organizations sending as your domain",
                    rows,
                    (0.40, 0.15, 0.15, 0.15, 0.15),
                )
            )
