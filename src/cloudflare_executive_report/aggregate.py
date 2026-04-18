"""Build report JSON from cached daily payloads."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from cloudflare_executive_report import __version__
from cloudflare_executive_report.common.constants import REPORT_JSON_SCHEMA_VERSION
from cloudflare_executive_report.common.dates import (
    format_ymd,
    iter_dates_inclusive,
    parse_ymd,
)

__all__ = [
    "build_report",
    "collect_days_payloads",
]


def build_report(
    *,
    zones_out: list[dict[str, Any]],
    warnings: list[str],
    period_start: str,
    period_end: str,
    requested_start: str,
    requested_end: str,
    report_type: str,
    data_fingerprint: dict[str, Any] | None = None,
    zone_health_fetched_at: str | None = None,
    partial: bool = False,
    missing_days: list[str] | None = None,
    schema_version: int = REPORT_JSON_SCHEMA_VERSION,
) -> dict[str, Any]:
    """Assemble the top-level report dict including schema and partial-cache metadata."""
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    days = list(missing_days) if missing_days is not None else []
    out: dict[str, Any] = {
        "schema_version": int(schema_version),
        "partial": bool(partial),
        "missing_days": days,
        "report_period": {
            "start": period_start,
            "end": period_end,
            "timezone": "UTC",
            "requested_start": requested_start,
            "requested_end": requested_end,
        },
        "generated_at": now,
        "tool_version": __version__,
        "report_type": str(report_type),
        "zones": zones_out,
        "warnings": warnings,
    }
    if data_fingerprint is not None:
        out["data_fingerprint"] = data_fingerprint
    out["zone_health_fetched_at"] = str(zone_health_fetched_at or now)
    return out


def collect_days_payloads(
    cache_read_fn: Any,
    zone_id: str,
    zone_name: str,
    start: str,
    end: str,
    *,
    label: str = "DNS",
) -> tuple[list[dict[str, Any]], list[str]]:
    """Read one cache file per day and return (api data list, warnings)."""
    warnings: list[str] = []
    api_days: list[dict[str, Any]] = []
    start_date, end_date = parse_ymd(start), parse_ymd(end)
    for day in iter_dates_inclusive(start_date, end_date):
        day_string = format_ymd(day)
        raw = cache_read_fn(zone_id, day_string)
        if not raw:
            warnings.append(
                f"{label} for zone {zone_name} on {day_string} unavailable (cache miss)"
            )
            continue
        src = raw.get("_source")
        if src == "null":
            warnings.append(
                f"{label} for zone {zone_name} on {day_string} unavailable (cached null)"
            )
            continue
        if src == "error":
            warnings.append(f"{label} for zone {zone_name} on {day_string} failed (cached error)")
            continue
        data = raw.get("data")
        if isinstance(data, dict):
            api_days.append(data)
        else:
            warnings.append(
                f"{label} for zone {zone_name} on {day_string} unavailable "
                "(cached entry has no data object)"
            )
    return api_days, warnings
