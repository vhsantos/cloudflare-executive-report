"""Retention policy helpers for analytics streams.

Functions in this module resolve retention windows by plan and evaluate whether
specific UTC calendar days are outside supported retention periods.
"""

from __future__ import annotations

from datetime import date

from cloudflare_executive_report.common.dates import utc_today


def dns_retention_days(plan_legacy_id: str | None) -> int:
    """Return DNS retention days based on zone plan tier."""
    lid = (plan_legacy_id or "free").lower()
    if lid == "enterprise":
        return 62
    if lid in ("pro", "business"):
        return 31
    return 7


def http_retention_days(_plan_legacy_id: str | None = None) -> int:
    """Return HTTP retention days for daily groups."""
    return 30


def security_retention_days(plan_legacy_id: str | None) -> int:
    """Return security retention days using the DNS tier grid."""
    return dns_retention_days(plan_legacy_id)


def date_outside_dns_retention(day: date, retention_days: int, *, ref: date | None = None) -> bool:
    """Return True when day is older than the retention window."""
    r = ref if ref is not None else utc_today()
    return (r - day).days > retention_days


def date_outside_http_retention(day: date, *, ref: date | None = None) -> bool:
    """Return True when day falls outside HTTP retention."""
    return date_outside_dns_retention(day, http_retention_days(), ref=ref)


def date_outside_security_retention(
    day: date,
    *,
    plan_legacy_id: str | None = None,
    ref: date | None = None,
) -> bool:
    """Return True when day falls outside security retention."""
    return date_outside_dns_retention(day, security_retention_days(plan_legacy_id), ref=ref)
