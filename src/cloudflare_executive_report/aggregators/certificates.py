"""Certificates stream aggregation builder."""

from __future__ import annotations

from typing import Any

from cloudflare_executive_report.common.aggregation_helpers import latest_snapshot_day


def build_certificates_section(
    daily_api_data: list[dict[str, Any]],
    *,
    top: int = 10,
) -> dict[str, Any]:
    """Aggregate certificate snapshots into one report section."""
    snapshot = latest_snapshot_day(daily_api_data)
    if not isinstance(snapshot, dict):
        return {}
    if snapshot.get("unavailable"):
        return {
            "unavailable": True,
            "reason": str(snapshot.get("reason") or "unknown"),
        }
    return {
        "total_certificate_packs": int(snapshot.get("total_certificate_packs") or 0),
        "expiring_in_30_days": int(snapshot.get("expiring_in_30_days") or 0),
        "soonest_expiry": snapshot.get("soonest_expiry"),
        "status_breakdown": list(snapshot.get("status_breakdown") or [])[:top],
    }
