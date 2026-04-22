"""Validation helpers for on-disk report JSON snapshots."""

from __future__ import annotations

from typing import Any

from cloudflare_executive_report.common.constants import REPORT_JSON_SCHEMA_VERSION


def is_report_snapshot_valid(report: dict[str, Any] | None) -> bool:
    """Return True if report dict has schema_version 1 and all required metadata fields."""
    if not isinstance(report, dict):
        return False
    if report.get("schema_version") != REPORT_JSON_SCHEMA_VERSION:
        return False
    if not isinstance(report.get("partial"), bool):
        return False
    md = report.get("missing_days")
    if not isinstance(md, list) or not all(isinstance(x, str) for x in md):
        return False
    period = report.get("report_period")
    if not isinstance(period, dict):
        return False
    if not str(period.get("start") or "").strip() or not str(period.get("end") or "").strip():
        return False
    if not str(report.get("report_type") or "").strip():
        return False
    fp = report.get("data_fingerprint")
    if not isinstance(fp, dict):
        return False
    if not str(report.get("zone_health_fetched_at") or "").strip():
        return False
    if not str(report.get("generated_at") or "").strip():
        return False
    if not str(report.get("tool_version") or "").strip():
        return False
    zones = report.get("zones")
    return isinstance(zones, list) and len(zones) >= 1


def data_fingerprint_matches(report: dict[str, Any] | None, expected: dict[str, Any]) -> bool:
    """Return True when report's data_fingerprint equals expected (full dict equality)."""
    if not isinstance(report, dict):
        return False
    got = report.get("data_fingerprint")
    if not isinstance(got, dict):
        return False
    return got == expected
