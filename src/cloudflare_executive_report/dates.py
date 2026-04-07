"""UTC date helpers (all report dates are UTC)."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta


def utc_today() -> date:
    return datetime.now(UTC).date()


def utc_yesterday() -> date:
    return utc_today() - timedelta(days=1)


def parse_ymd(s: str) -> date:
    return date.fromisoformat(s)


def format_ymd(d: date) -> str:
    return d.isoformat()


def day_bounds_utc(d: date) -> tuple[str, str]:
    """ISO 8601 Z bounds [datetime_geq, datetime_lt) for one UTC calendar day."""
    start = datetime(d.year, d.month, d.day, tzinfo=UTC)
    end = start + timedelta(days=1)
    return start.strftime("%Y-%m-%dT%H:%M:%SZ"), end.strftime("%Y-%m-%dT%H:%M:%SZ")


def day_start_iso_z(d: date) -> str:
    """First instant of a UTC calendar day (midnight)."""
    return f"{format_ymd(d)}T00:00:00Z"


def utc_now_iso_z() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso_datetime_z(value: object) -> datetime | None:
    """Parse ISO datetime strings, accepting both Z and offset forms."""
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
    """Format ISO datetime as YYYY-MM-DD plus day delta from as_of."""
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
    if end < start:
        return
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def last_n_complete_days(n: int, *, yesterday: date | None = None) -> tuple[date, date]:
    """Last N complete UTC days ending at yesterday (inclusive)."""
    if n < 1:
        raise ValueError("n must be >= 1")
    y = yesterday if yesterday is not None else utc_yesterday()
    start = y - timedelta(days=n - 1)
    return start, y
