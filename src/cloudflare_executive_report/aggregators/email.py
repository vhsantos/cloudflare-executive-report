"""Email routing data aggregation."""

from __future__ import annotations

from typing import Any

from cloudflare_executive_report.common.constants import UNAVAILABLE
from cloudflare_executive_report.common.formatting import format_count_human


def build_email_section(
    daily_api_data: list[dict[str, Any]],
    *,
    top: int = 10,
) -> dict[str, Any]:
    """Aggregate email routing daily payloads into one report section."""

    # Latest state (from the last day in the range)
    email_routing_enabled = False
    email_routing_status = UNAVAILABLE
    routing_rules_count = 0
    dns_dmarc_policy = UNAVAILABLE
    dns_spf_policy = UNAVAILABLE
    dns_dkim_configured = False

    if daily_api_data:
        latest = daily_api_data[-1]
        email_routing_enabled = bool(latest.get("email_routing_enabled"))
        email_routing_status = str(latest.get("email_routing_status") or UNAVAILABLE)
        routing_rules_count = int(latest.get("routing_rules_count") or 0)
        dns_dmarc_policy = str(latest.get("dns_dmarc_policy") or UNAVAILABLE)
        dns_spf_policy = str(latest.get("dns_spf_policy") or UNAVAILABLE)
        dns_dkim_configured = bool(latest.get("dns_dkim_configured"))

    # Aggregated metrics
    total_received = 0
    forwarded = 0
    dropped = 0
    rejected = 0
    delivery_failed = 0

    dmarc_total_matching = 0
    dmarc_pass = 0
    spf_pass = 0
    dkim_pass = 0

    timeseries: list[dict[str, Any]] = []

    # Map for Top Sources
    sources: dict[str, dict[str, int]] = {}

    for day in daily_api_data:
        date_str = str(day.get("date") or "")

        # Daily ER metrics
        day_forwarded = 0
        day_dropped = 0
        day_rejected = 0
        day_failed = 0

        for metric in day.get("erg_metrics") or []:
            if not isinstance(metric, dict):
                continue
            action = str(metric.get("action") or "").lower()
            status = str(metric.get("status") or "").lower()
            count = int(metric.get("count") or 0)

            total_received += count

            if action == "forward":
                if status == "delivered":
                    forwarded += count
                    day_forwarded += count
                elif status == "deliveryfailed":
                    delivery_failed += count
                    day_failed += count
                else:
                    # Treat other forward statuses as failed for safety
                    delivery_failed += count
                    day_failed += count
            elif action == "drop":
                dropped += count
                day_dropped += count
            elif action == "reject":
                rejected += count
                day_rejected += count
            else:
                # Fallback for unexpected actions
                delivery_failed += count
                day_failed += count

        if date_str:
            timeseries.append(
                {
                    "date": date_str,
                    "forwarded": day_forwarded,
                    "delivery_failed": day_failed,
                    "dropped_rejected": day_dropped + day_rejected,
                }
            )

        # Daily DMARC/SPF/DKIM totals
        for metric in day.get("erg_dmarc_metrics") or []:
            if not isinstance(metric, dict):
                continue
            dmarc_total_matching += int(metric.get("totalMatchingMessages") or 0)
            dmarc_pass += int(metric.get("dmarc") or 0)
            spf_pass += int(metric.get("spfPass") or 0)
            dkim_pass += int(metric.get("dkimPass") or 0)

        # Top Sources
        for source in day.get("erg_dmarc_top_sources") or []:
            if not isinstance(source, dict):
                continue
            name = str(source.get("sourceOrgName") or "").strip()
            if not name:
                continue

            if name not in sources:
                sources[name] = {
                    "totalMatchingMessages": 0,
                    "dmarcPass": 0,
                    "spfPass": 0,
                    "dkimPass": 0,
                }

            sources[name]["totalMatchingMessages"] += int(source.get("totalMatchingMessages") or 0)
            sources[name]["dmarcPass"] += int(source.get("dmarc") or 0)
            sources[name]["spfPass"] += int(source.get("spfPass") or 0)
            sources[name]["dkimPass"] += int(source.get("dkimPass") or 0)

    dmarc_pass_rate_pct = (
        (100.0 * dmarc_pass / dmarc_total_matching) if dmarc_total_matching > 0 else 0.0
    )
    spf_aligned_rate_pct = (
        (100.0 * spf_pass / dmarc_total_matching) if dmarc_total_matching > 0 else 0.0
    )
    dkim_aligned_rate_pct = (
        (100.0 * dkim_pass / dmarc_total_matching) if dmarc_total_matching > 0 else 0.0
    )
    delivery_failed_rate_pct = (
        (100.0 * delivery_failed / total_received) if total_received > 0 else 0.0
    )

    # Sort sources by totalMatchingMessages and calculate percentages
    top_sources: list[dict[str, Any]] = []
    sorted_sources = sorted(sources.items(), key=lambda x: -x[1]["totalMatchingMessages"])

    for name, stats in sorted_sources[:top]:
        total = stats["totalMatchingMessages"]
        top_sources.append(
            {
                "sourceOrgName": name,
                "volume": total,
                "volume_human": format_count_human(total),
                "dmarc_pass_pct": (100.0 * stats["dmarcPass"] / total) if total > 0 else 0.0,
                "spf_aligned_pct": (100.0 * stats["spfPass"] / total) if total > 0 else 0.0,
                "dkim_aligned_pct": (100.0 * stats["dkimPass"] / total) if total > 0 else 0.0,
            }
        )

    return {
        "email_routing_enabled": email_routing_enabled,
        "email_routing_status": email_routing_status,
        "routing_rules_count": routing_rules_count,
        "dns_dmarc_policy": dns_dmarc_policy,
        "dns_spf_policy": dns_spf_policy,
        "dns_dkim_configured": dns_dkim_configured,
        "total_received": total_received,
        "total_received_human": format_count_human(total_received),
        "forwarded": forwarded,
        "forwarded_human": format_count_human(forwarded),
        "dropped": dropped,
        "dropped_human": format_count_human(dropped),
        "rejected": rejected,
        "rejected_human": format_count_human(rejected),
        "delivery_failed": delivery_failed,
        "delivery_failed_human": format_count_human(delivery_failed),
        "delivery_failed_rate_pct": delivery_failed_rate_pct,
        "dmarc_pass_rate_pct": dmarc_pass_rate_pct,
        "spf_aligned_rate_pct": spf_aligned_rate_pct,
        "dkim_aligned_rate_pct": dkim_aligned_rate_pct,
        "timeseries": timeseries,
        "top_sources": top_sources,
    }
