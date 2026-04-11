"""Executive summary page for CTO-oriented PDF reports."""

from __future__ import annotations

from typing import Any

from reportlab.platypus import Paragraph, Spacer

from cloudflare_executive_report.common.constants import (
    PDF_SPACE_MEDIUM_PT,
    PDF_SPACE_SMALL_PT,
)
from cloudflare_executive_report.common.formatting import (
    format_count_compact,
    format_number_compact,
    format_pdf_status_line,
    format_percent_compact,
)
from cloudflare_executive_report.pdf.primitives import kpi_multi_cell_row, make_styles
from cloudflare_executive_report.pdf.theme import Theme


def _report_type_suffix(report_type: str | None) -> str:
    rt = str(report_type or "").strip().lower()
    if not rt or rt in {"custom", "incremental"}:
        return ""
    fixed = {
        "last_month": "Last Month",
        "this_month": "This Month (to date)",
        "last_week": "Last Week",
        "this_week": "This Week (to date)",
        "yesterday": "Yesterday",
        "last_year": "Last Year",
        "this_year": "This Year (to date)",
    }
    if rt in fixed:
        return f" - {fixed[rt]}"
    if rt.startswith("last_"):
        n = rt[5:]
        if n.isdigit() and int(n) > 0:
            days = int(n)
            unit = "Day" if days == 1 else "Days"
            return f" - Last {days} {unit}"
    return ""


def _indicator_for(summary: dict[str, Any], key: str) -> str:
    indicators = summary.get("kpi_indicators")
    if isinstance(indicators, dict):
        return str(indicators.get(key) or "").strip()
    return ""


def append_executive_summary(
    story: list[Any],
    *,
    zone_name: str,
    period_start: str,
    period_end: str,
    summary: dict[str, Any],
    report_type: str | None,
    theme: Theme,
) -> None:
    styles = make_styles(theme)
    w_content = theme.content_width_in()

    verdict = str(summary.get("verdict") or "warning").upper()
    story.append(Paragraph("Executive summary", styles["RepStreamHeadLeft"]))
    story.append(
        Paragraph(
            f"<font color='{theme.primary}'><b>{zone_name}</b></font>"
            f"<font color='{theme.muted}'> · {period_start} to {period_end} (UTC)"
            f"{_report_type_suffix(report_type)}</font>",
            styles["RepSubtitle"],
        )
    )
    story.append(Spacer(1, PDF_SPACE_SMALL_PT))

    kpis = summary.get("kpis") or {}
    platform = kpis.get("platform") or {}
    traffic = kpis.get("traffic") or {}
    security = kpis.get("security") or {}
    dns = kpis.get("dns") or {}
    dns_records = kpis.get("dns_records") or {}
    audit_k = kpis.get("audit") or {}
    certificates_k = kpis.get("certificates") or {}

    story.append(
        kpi_multi_cell_row(
            [
                ("Verdict", verdict),
                ("Zone status", str(platform.get("zone_status") or "unavailable")),
                ("TLS/SSL Mode", str(platform.get("ssl_mode") or "unavailable")),
                ("Always HTTPS", str(platform.get("always_https") or "unavailable")),
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
                (
                    "Requests",
                    format_count_compact(traffic.get("total_requests")),
                    _indicator_for(summary, "traffic.total_requests"),
                ),
                (
                    "Encrypted requests",
                    format_count_compact(traffic.get("encrypted_requests")),
                    _indicator_for(summary, "traffic.encrypted_requests"),
                ),
                (
                    "Cache hit ratio",
                    format_percent_compact(traffic.get("cache_hit_ratio")),
                    _indicator_for(summary, "traffic.cache_hit_ratio"),
                ),
                (
                    "Blocked/Challenged",
                    format_count_compact(security.get("mitigated_events")),
                    _indicator_for(summary, "security.mitigated_events"),
                ),
                (
                    "Mitigation rate",
                    format_percent_compact(security.get("mitigation_rate_pct")),
                    _indicator_for(summary, "security.mitigation_rate_pct"),
                ),
            ],
            styles,
            theme=theme,
            content_width_in=w_content,
        )
    )
    story.append(Spacer(1, PDF_SPACE_MEDIUM_PT))
    p50 = traffic.get("latency_p50_ms")
    p95 = traffic.get("latency_p95_ms")
    lat_txt = (
        f"{float(p50):.0f}/{float(p95):.0f} ms" if p50 is not None and p95 is not None else "-"
    )
    origin_ms = traffic.get("origin_response_duration_avg_ms")
    origin_txt = f"{round(float(origin_ms))} ms" if origin_ms is not None else "-"
    story.append(
        kpi_multi_cell_row(
            [
                (
                    "4xx rate",
                    format_percent_compact(traffic.get("status_4xx_rate_pct")),
                    _indicator_for(summary, "traffic.status_4xx_rate_pct"),
                ),
                (
                    "5xx rate",
                    format_percent_compact(traffic.get("status_5xx_rate_pct")),
                    _indicator_for(summary, "traffic.status_5xx_rate_pct"),
                ),
                ("Edge p50/p95", lat_txt, _indicator_for(summary, "traffic.latency_p95_ms")),
                (
                    "Origin response",
                    origin_txt,
                    _indicator_for(summary, "traffic.origin_response_duration_avg_ms"),
                ),
            ],
            styles,
            theme=theme,
            content_width_in=w_content,
        )
    )
    story.append(Spacer(1, PDF_SPACE_MEDIUM_PT))
    dr_un = bool(dns_records.get("unavailable"))
    au_un = bool(audit_k.get("unavailable"))
    ce_un = bool(certificates_k.get("unavailable"))
    story.append(
        kpi_multi_cell_row(
            [
                (
                    "DNS queries",
                    format_count_compact(dns.get("total_queries")),
                    _indicator_for(summary, "dns.total_queries"),
                ),
                (
                    "Avg DNS QPS",
                    format_number_compact(dns.get("average_qps")),
                    _indicator_for(summary, "dns.average_qps"),
                ),
                (
                    "DNS records",
                    "unavailable" if dr_un else str(dns_records.get("total_records") or "0"),
                ),
                (
                    "Proxied",
                    "-" if dr_un else str(dns_records.get("proxied_records") or "0"),
                    _indicator_for(summary, "dns_records.proxied_records"),
                ),
                (
                    "DNS-only",
                    "-" if dr_un else str(dns_records.get("dns_only_records") or "0"),
                    _indicator_for(summary, "dns_records.dns_only_records"),
                ),
            ],
            styles,
            theme=theme,
            content_width_in=w_content,
        )
    )
    story.append(Spacer(1, PDF_SPACE_MEDIUM_PT))
    cert_human = str(certificates_k.get("cert_expires_human") or "-")
    cert_exp30 = int(certificates_k.get("expiring_in_30_days") or 0)
    if cert_human != "-" and "(" in cert_human and ")" in cert_human:
        cert_days = cert_human.split("(", 1)[1].split(")", 1)[0].strip()
    else:
        cert_days = cert_human
    cert_label = "unavailable" if ce_un else cert_days
    if not ce_un and cert_exp30 > 0 and cert_label != "-":
        cert_label = f"expiring soon: {cert_label}"
    cert_packs_v = (
        "unavailable" if ce_un else str(certificates_k.get("total_certificate_packs") or "0")
    )
    cert_exp30_v = "unavailable" if ce_un else str(certificates_k.get("expiring_in_30_days") or "0")
    apex_status = "-" if dr_un else str(dns_records.get("apex_protection_status") or "-")
    audit_events = "unavailable" if au_un else str(audit_k.get("total_events") or "0")
    story.append(
        kpi_multi_cell_row(
            [
                ("Audit events", audit_events),
                ("Cert packs", cert_packs_v),
                ("Expiring ≤30d", cert_exp30_v),
                ("Cert expires", cert_label),
                ("Apex protection", apex_status),
            ],
            styles,
            theme=theme,
            content_width_in=w_content,
        )
    )
    story.append(Spacer(1, PDF_SPACE_SMALL_PT))

    takeaways = [str(x) for x in (summary.get("takeaways") or []) if str(x).strip()]
    actions = [str(x) for x in (summary.get("actions") or []) if str(x).strip()]
    if takeaways:
        story.append(Paragraph("Takeaways", styles["RepSection"]))
        for row in takeaways[:8]:
            story.append(Paragraph(format_pdf_status_line(row), styles["RepTableCell"]))
        story.append(Spacer(1, PDF_SPACE_MEDIUM_PT))
    if actions:
        story.append(Paragraph("Actions", styles["RepSection"]))
        for row in actions:
            story.append(
                Paragraph(format_pdf_status_line(row, level="action"), styles["RepTableCell"])
            )
