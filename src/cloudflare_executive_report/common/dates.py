"""Date and time helpers for UTC-only report logic.

All helpers in this module assume UTC semantics and return values suitable for
cache keys, report ranges, and Cloudflare API datetime filters.
"""

from __future__ import annotations

import calendar
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta


def utc_today() -> date:
    """Return the current UTC calendar date."""
    return datetime.now(UTC).date()


def utc_yesterday() -> date:
    """Return yesterday in UTC calendar terms."""
    return utc_today() - timedelta(days=1)


def parse_ymd(s: str) -> date:
    """Parse a YYYY-MM-DD date string into a date object."""
    return date.fromisoformat(s)


def format_ymd(d: date) -> str:
    """Format a date object as YYYY-MM-DD."""
    return d.isoformat()


def day_bounds_utc(d: date) -> tuple[str, str]:
    """Return ISO Z bounds [geq, lt) for a single UTC day."""
    start = datetime(d.year, d.month, d.day, tzinfo=UTC)
    end = start + timedelta(days=1)
    return start.strftime("%Y-%m-%dT%H:%M:%SZ"), end.strftime("%Y-%m-%dT%H:%M:%SZ")


def day_start_iso_z(d: date) -> str:
    """Return the ISO Z timestamp for UTC midnight of the provided day."""
    return f"{format_ymd(d)}T00:00:00Z"


def utc_now_iso_z() -> str:
    """Return current UTC timestamp formatted as ISO 8601 with Z suffix."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso_datetime_z(value: object) -> datetime | None:
    """Parse ISO datetime text, accepting both Z and explicit offsets."""
    s = str(value or "").strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def format_date_with_days_from_iso(iso_value: object, *, as_of: date) -> str:
    """Format ISO datetime as YYYY-MM-DD plus delta in days from as_of."""
    dt = parse_iso_datetime_z(iso_value)
    if dt is None:
        return "-"
    exp = dt.astimezone(UTC).date()
    days = (exp - as_of).days
    if days < 0:
        return f"{exp.isoformat()} ({abs(days)} days ago)"
    if days == 0:
        return f"{exp.isoformat()} (today)"
    return f"{exp.isoformat()} ({days} days)"


def iter_dates_inclusive(start: date, end: date) -> Iterator[date]:
    """Yield each date in the inclusive [start, end] range."""
    if end < start:
        return
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def last_n_complete_days(n: int, *, yesterday: date | None = None) -> tuple[date, date]:
    """Return the inclusive date window for the last N complete UTC days."""
    if n < 1:
        raise ValueError("n must be >= 1")
    y = yesterday if yesterday is not None else utc_yesterday()
    start = y - timedelta(days=n - 1)
    return start, y


def week_bounds(d: date) -> tuple[date, date]:
    """Return Monday-Sunday bounds for the week containing d."""
    start = d - timedelta(days=d.weekday())
    end = start + timedelta(days=6)
    return start, end


def month_bounds(d: date) -> tuple[date, date]:
    """Return first-day and last-day bounds for the month containing d."""
    last_day = calendar.monthrange(d.year, d.month)[1]
    start = date(d.year, d.month, 1)
    end = date(d.year, d.month, last_day)
    return start, end


def year_bounds(d: date) -> tuple[date, date]:
    """Return first-day and last-day bounds for the year containing d."""
    return date(d.year, 1, 1), date(d.year, 12, 31)
