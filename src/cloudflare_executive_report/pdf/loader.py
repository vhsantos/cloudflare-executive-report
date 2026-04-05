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
    scratch = _load_cached_stream_days(
        cache_root,
        zone_id,
        zone_name,
        start,
        end,
        stream_id="http",
        stream_label="HTTP",
        metric_key="requests",
    )
    rollup, missing, warns, n_api = _finalize_stream_load(
        scratch, top=top, build_rollup=build_http_section
    )
    return HttpLoadResult(
        rollup=rollup,
        daily_requests=scratch.daily_metric,
        missing_dates=missing,
        warnings=warns,
        api_day_count=n_api,
    )
