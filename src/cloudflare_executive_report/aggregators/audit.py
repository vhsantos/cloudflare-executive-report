"""Audit stream aggregation builder."""

from __future__ import annotations

from typing import Any

from cloudflare_executive_report.common.aggregation_helpers import merge_value_count_rows


def build_audit_section(
    daily_api_data: list[dict[str, Any]],
    *,
    top: int = 10,
) -> dict[str, Any]:
    """Aggregate audit snapshots into one report section."""
    if not daily_api_data:
        return {}
    days_ok = [
        day for day in daily_api_data if isinstance(day, dict) and not day.get("unavailable")
    ]
    days_unavailable = [
        day for day in daily_api_data if isinstance(day, dict) and day.get("unavailable")
    ]
    if not days_ok and days_unavailable:
        return {
            "unavailable": True,
            "reason": str(days_unavailable[0].get("reason") or "unknown"),
        }
    total_events = sum(int(day.get("total_events") or 0) for day in days_ok)
    return {
        "total_events": total_events,
        "top_actions": merge_value_count_rows(daily_api_data, "top_actions", top=top),
        "top_actors": merge_value_count_rows(daily_api_data, "top_actors", top=top),
    }
