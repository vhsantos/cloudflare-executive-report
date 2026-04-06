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
