"""DNS records stream aggregation builder."""

from __future__ import annotations

from typing import Any

from cloudflare_executive_report.common.aggregation_helpers import latest_snapshot_day


def build_dns_records_section(
    daily_api_data: list[dict[str, Any]],
    *,
    top: int = 10,
) -> dict[str, Any]:
    """Aggregate DNS records snapshots into one report section."""
    snapshot = latest_snapshot_day(daily_api_data)
    if not isinstance(snapshot, dict):
        return {}
    if snapshot.get("unavailable"):
        return {
            "unavailable": True,
            "reason": str(snapshot.get("reason") or "unknown"),
        }
    rows = list(snapshot.get("record_types") or [])[:top]
    return {
        "total_records": int(snapshot.get("total_records") or 0),
        "proxied_records": int(snapshot.get("proxied_records") or 0),
        "dns_only_records": int(snapshot.get("dns_only_records") or 0),
        "apex_unproxied_a_aaaa": int(snapshot.get("apex_unproxied_a_aaaa") or 0),
        "record_types": rows,
    }
