"""Cache coverage helpers for report windows (missing stream days, completeness checks)."""

from __future__ import annotations

from pathlib import Path

from cloudflare_executive_report.cache import read_day_file
from cloudflare_executive_report.common.dates import (
    format_ymd,
    iter_dates_inclusive,
    parse_ymd,
    utc_yesterday,
)
from cloudflare_executive_report.common.report_period import report_bounds_from_indices
from cloudflare_executive_report.config import AppConfig
from cloudflare_executive_report.fetchers.registry import day_cache_path
from cloudflare_executive_report.sync.options import SyncOptions


def cached_stream_payload_usable(raw: dict | None) -> bool:
    """True when a cache day file has usable analytics payload (not miss, null, or error)."""
    if not raw:
        return False
    src = raw.get("_source")
    if src in ("null", "error"):
        return False
    return isinstance(raw.get("data"), dict)


def missing_stream_days_for_zone(
    cache_root: Path,
    zone_id: str,
    report_start: str,
    cache_end: str,
    stream_ids: list[str],
) -> set[str]:
    """Dates in the inclusive window where any selected stream lacks usable cache."""
    missing: set[str] = set()
    try:
        s, e = parse_ymd(report_start), parse_ymd(cache_end)
    except ValueError:
        return missing
    if s > e:
        return missing
    for d in iter_dates_inclusive(s, e):
        ds = format_ymd(d)
        for sid in stream_ids:
            raw = read_day_file(day_cache_path(cache_root, zone_id, ds, sid))
            if not cached_stream_payload_usable(raw):
                missing.add(ds)
                break
    return missing


def report_period_streams_cache_complete(
    cfg: AppConfig,
    opts: SyncOptions,
    *,
    zone_filter: str | None,
    streams: tuple[str, ...],
) -> bool:
    """True when every requested stream day in the report window has usable cache on disk."""
    cache_root = cfg.cache_path()
    zones = list(cfg.zones)
    if zone_filter:
        zf = zone_filter.strip()
        zones = [z for z in zones if z.id == zf or z.name == zf]
        if not zones:
            return False
    if not zones:
        return False
    y = utc_yesterday()
    report_start, report_end = report_bounds_from_indices(zones, cache_root, y, opts)
    cache_end = format_ymd(y) if opts.include_today else report_end
    stream_ids = [s.strip().lower() for s in streams if str(s).strip()]
    if not stream_ids:
        return True
    all_missing: set[str] = set()
    for z in zones:
        all_missing |= missing_stream_days_for_zone(
            cache_root, z.id, report_start, cache_end, stream_ids
        )
    return len(all_missing) == 0
