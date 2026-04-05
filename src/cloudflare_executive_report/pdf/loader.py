"""Load per-day cache files for PDF streams."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from cloudflare_executive_report.aggregate import build_dns_section, build_http_section
from cloudflare_executive_report.cache.envelope import read_day_file
from cloudflare_executive_report.dates import format_ymd, iter_dates_inclusive, parse_ymd
from cloudflare_executive_report.fetchers.registry import day_cache_path

log = logging.getLogger(__name__)


@dataclass
class DnsLoadResult:
    rollup: dict[str, Any]
    daily_queries: list[tuple[date, int | None]]
    missing_dates: list[str]
    warnings: list[str] = field(default_factory=list)
    api_day_count: int = 0


@dataclass
class HttpLoadResult:
    rollup: dict[str, Any]
    daily_requests: list[tuple[date, int | None]]
    daily_requests_cached: list[tuple[date, int | None]]
    daily_requests_uncached: list[tuple[date, int | None]]
    daily_bytes_cached: list[tuple[date, int | None]]
    daily_bytes_uncached: list[tuple[date, int | None]]
    daily_uniques: list[tuple[date, int | None]]
    missing_dates: list[str]
    warnings: list[str] = field(default_factory=list)
    api_day_count: int = 0


@dataclass
class _StreamDaysScratch:
    """Internal: API payloads and aligned daily metric for charts."""

    api_days: list[dict[str, Any]]
    daily_metric: list[tuple[date, int | None]]
    missing_dates: list[str]
    warnings: list[str]


def _load_cached_stream_days(
    cache_root: Path,
    zone_id: str,
    zone_name: str,
    start: str,
    end: str,
    *,
    stream_id: str,
    stream_label: str,
    metric_key: str,
) -> _StreamDaysScratch:
    warnings: list[str] = []
    api_days: list[dict[str, Any]] = []
    daily_metric: list[tuple[date, int | None]] = []
    missing_dates: list[str] = []

    for d in iter_dates_inclusive(parse_ymd(start), parse_ymd(end)):
        ds = format_ymd(d)
        path = day_cache_path(cache_root, zone_id, ds, stream_id)
        raw = read_day_file(path)
        if not raw:
            warnings.append(f"No {stream_label} cache for zone {zone_name} on {ds}")
            missing_dates.append(ds)
            daily_metric.append((d, None))
            continue
        src = raw.get("_source")
        if src == "null":
            warnings.append(f"{stream_label} for zone {zone_name} on {ds} unavailable (null)")
            missing_dates.append(ds)
            daily_metric.append((d, None))
            continue
        if src == "error":
            warnings.append(f"{stream_label} for zone {zone_name} on {ds} failed (cached error)")
            missing_dates.append(ds)
            daily_metric.append((d, None))
            continue
        data = raw.get("data")
        if not isinstance(data, dict):
            warnings.append(f"{stream_label} for zone {zone_name} on {ds} has no data object")
            missing_dates.append(ds)
            daily_metric.append((d, None))
            continue
        api_days.append(data)
        daily_metric.append((d, int(data.get(metric_key) or 0)))

    return _StreamDaysScratch(
        api_days=api_days,
        daily_metric=daily_metric,
        missing_dates=missing_dates,
        warnings=warnings,
    )


def _finalize_stream_load(
    scratch: _StreamDaysScratch,
    *,
    top: int,
    build_rollup: Callable[[list[dict[str, Any]], int], dict[str, Any]],
) -> tuple[dict[str, Any], list[str], list[str], int]:
    rollup = build_rollup(scratch.api_days, top=top) if scratch.api_days else {}
    for w in scratch.warnings:
        log.warning("%s", w)
    return rollup, scratch.missing_dates, scratch.warnings, len(scratch.api_days)


def _load_http_days_for_range(
    cache_root: Path,
    zone_id: str,
    zone_name: str,
    start: str,
    end: str,
) -> tuple[
    list[dict[str, Any]],
    list[tuple[date, int | None]],
    list[tuple[date, int | None]],
    list[tuple[date, int | None]],
    list[tuple[date, int | None]],
    list[tuple[date, int | None]],
    list[tuple[date, int | None]],
    list[str],
    list[str],
]:
    """One pass over HTTP cache: totals plus cached/uncached splits and uniques per day."""
    warnings: list[str] = []
    api_days: list[dict[str, Any]] = []
    daily_total: list[tuple[date, int | None]] = []
    daily_rc: list[tuple[date, int | None]] = []
    daily_ru: list[tuple[date, int | None]] = []
    daily_bc: list[tuple[date, int | None]] = []
    daily_bu: list[tuple[date, int | None]] = []
    daily_uv: list[tuple[date, int | None]] = []
    missing_dates: list[str] = []

    for d in iter_dates_inclusive(parse_ymd(start), parse_ymd(end)):
        ds = format_ymd(d)
        path = day_cache_path(cache_root, zone_id, ds, "http")
        raw = read_day_file(path)
        if not raw:
            warnings.append(f"No HTTP cache for zone {zone_name} on {ds}")
            missing_dates.append(ds)
            daily_total.append((d, None))
            daily_rc.append((d, None))
            daily_ru.append((d, None))
            daily_bc.append((d, None))
            daily_bu.append((d, None))
            daily_uv.append((d, None))
            continue
        src = raw.get("_source")
        if src == "null":
            warnings.append(f"HTTP for zone {zone_name} on {ds} unavailable (null)")
            missing_dates.append(ds)
            daily_total.append((d, None))
            daily_rc.append((d, None))
            daily_ru.append((d, None))
            daily_bc.append((d, None))
            daily_bu.append((d, None))
            daily_uv.append((d, None))
            continue
        if src == "error":
            warnings.append(f"HTTP for zone {zone_name} on {ds} failed (cached error)")
            missing_dates.append(ds)
            daily_total.append((d, None))
            daily_rc.append((d, None))
            daily_ru.append((d, None))
            daily_bc.append((d, None))
            daily_bu.append((d, None))
            daily_uv.append((d, None))
            continue
        data = raw.get("data")
        if not isinstance(data, dict):
            warnings.append(f"HTTP for zone {zone_name} on {ds} has no data object")
            missing_dates.append(ds)
            daily_total.append((d, None))
            daily_rc.append((d, None))
            daily_ru.append((d, None))
            daily_bc.append((d, None))
            daily_bu.append((d, None))
            daily_uv.append((d, None))
            continue

        api_days.append(data)
        tr = int(data.get("requests") or 0)
        cr = int(data.get("cached_requests") or 0)
        ur = max(0, tr - cr)
        tb = int(data.get("bytes") or 0)
        cb = int(data.get("cached_bytes") or 0)
        ub = max(0, tb - cb)
        uq = int(data.get("uniques") or 0)

        daily_total.append((d, tr))
        daily_rc.append((d, cr))
        daily_ru.append((d, ur))
        daily_bc.append((d, cb))
        daily_bu.append((d, ub))
        daily_uv.append((d, uq))

    return (
        api_days,
        daily_total,
        daily_rc,
        daily_ru,
        daily_bc,
        daily_bu,
        daily_uv,
        missing_dates,
        warnings,
    )


def load_dns_for_range(
    cache_root: Path,
    zone_id: str,
    zone_name: str,
    start: str,
    end: str,
    *,
    top: int,
) -> DnsLoadResult:
    scratch = _load_cached_stream_days(
        cache_root,
        zone_id,
        zone_name,
        start,
        end,
        stream_id="dns",
        stream_label="DNS",
        metric_key="total_queries",
    )
    rollup, missing, warns, n_api = _finalize_stream_load(
        scratch, top=top, build_rollup=build_dns_section
    )
    return DnsLoadResult(
        rollup=rollup,
        daily_queries=scratch.daily_metric,
        missing_dates=missing,
        warnings=warns,
        api_day_count=n_api,
    )


def load_http_for_range(
    cache_root: Path,
    zone_id: str,
    zone_name: str,
    start: str,
    end: str,
    *,
    top: int,
) -> HttpLoadResult:
    api_days, dt, drc, dru, dbc, dbu, duv, missing, warns = _load_http_days_for_range(
        cache_root, zone_id, zone_name, start, end
    )
    scratch = _StreamDaysScratch(
        api_days=api_days,
        daily_metric=dt,
        missing_dates=missing,
        warnings=warns,
    )
    rollup, missing2, _, n_api = _finalize_stream_load(
        scratch, top=top, build_rollup=build_http_section
    )
    return HttpLoadResult(
        rollup=rollup,
        daily_requests=dt,
        daily_requests_cached=drc,
        daily_requests_uncached=dru,
        daily_bytes_cached=dbc,
        daily_bytes_uncached=dbu,
        daily_uniques=duv,
        missing_dates=missing2,
        warnings=warns,
        api_day_count=n_api,
    )
