"""Executive summary page for CTO-oriented PDF reports."""

from __future__ import annotations

from typing import Any

from reportlab.platypus import Paragraph, Spacer

from cloudflare_executive_report.pdf.primitives import kpi_multi_cell_row, make_styles
from cloudflare_executive_report.pdf.theme import Theme


def append_executive_summary(
    story: list[Any],
    *,
    zone_name: str,
    period_start: str,
    period_end: str,
    summary: dict[str, Any],
    theme: Theme,
) -> None:
    styles = make_styles(theme)
    w_content = theme.content_width_in()

    verdict = str(summary.get("verdict") or "warning").upper()
    story.append(Paragraph("Executive summary", styles["RepStreamHeadLeft"]))
    story.append(
        Paragraph(
            f"<font color='{theme.primary}'><b>{zone_name}</b></font>"
            f"<font color='{theme.muted}'> · {period_start} to {period_end} (UTC)</font>",
            styles["RepSubtitle"],
        )
    )
    story.append(Spacer(1, 4))

    kpis = summary.get("kpis") or {}
    platform = kpis.get("platform") or {}
    traffic = kpis.get("traffic") or {}
    security = kpis.get("security") or {}
    dns = kpis.get("dns") or {}

    story.append(
        kpi_multi_cell_row(
            [
                ("Verdict", verdict),
                ("Zone status", str(platform.get("zone_status") or "unavailable")),
                ("SSL mode", str(platform.get("ssl_mode") or "unavailable")),
                ("Always HTTPS", str(platform.get("always_https") or "unavailable")),
            ],
            styles,
            theme=theme,
            content_width_in=w_content,
        )
    )
    story.append(Spacer(1, 10))
    story.append(
        kpi_multi_cell_row(
            [
                ("Requests", str(traffic.get("total_requests_human") or "0")),
                ("Cache hit ratio", f"{float(traffic.get('cache_hit_ratio') or 0.0):.1f}%"),
                ("Threats blocked/challenged", str(security.get("mitigated_events_human") or "0")),
                ("Mitigation rate", f"{float(security.get('mitigation_rate_pct') or 0.0):.1f}%"),
            ],
            styles,
            theme=theme,
            content_width_in=w_content,
        )
    )
    story.append(Spacer(1, 10))
    story.append(
        kpi_multi_cell_row(
            [
                ("DNS queries", str(dns.get("total_queries_human") or "0")),
                ("Avg DNS QPS", f"{float(dns.get('average_qps') or 0.0):.3f}"),
                ("Encrypted requests", str(traffic.get("encrypted_requests_human") or "0")),
            ],
            styles,
            theme=theme,
            content_width_in=w_content,
        )
    )
    story.append(Spacer(1, 16))

    takeaways = [str(x) for x in (summary.get("takeaways") or []) if str(x).strip()]
    actions = [str(x) for x in (summary.get("actions") or []) if str(x).strip()]
    if takeaways:
        story.append(Paragraph("Takeaways", styles["RepSection"]))
        for row in takeaways[:3]:
            story.append(Paragraph(f"- {row}", styles["RepTableCell"]))
        story.append(Spacer(1, 10))
    if actions:
        story.append(Paragraph("Actions", styles["RepSection"]))
        for row in actions[:3]:
            story.append(Paragraph(f"- {row}", styles["RepTableCell"]))
