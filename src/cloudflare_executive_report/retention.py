"""DNS analytics retention vs zone plan (UTC calendar dates)."""

from __future__ import annotations

from datetime import date

from cloudflare_executive_report.dates import utc_today


def dns_retention_days(plan_legacy_id: str | None) -> int:
    lid = (plan_legacy_id or "free").lower()
    if lid == "enterprise":
        return 62
    if lid in ("pro", "business"):
        return 31
    return 7


def date_outside_dns_retention(day: date, retention_days: int, *, ref: date | None = None) -> bool:
    """True if day is older than retention window (exclusive of boundary)."""
    r = ref if ref is not None else utc_today()
    return (r - day).days > retention_days
