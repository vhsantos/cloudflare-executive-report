"""Load per-day cache files for PDF streams."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from cloudflare_executive_report.aggregate import (
    build_audit_section,
    build_cache_section,
    build_certificates_section,
    build_dns_records_section,
    build_dns_section,
    build_http_adaptive_section,
    build_http_section,
    build_security_section,
)
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
class SecurityLoadResult:
    rollup: dict[str, Any]
    daily_security_triple: list[tuple[date, tuple[int | None, int | None, int | None]]]
    missing_dates: list[str]
    warnings: list[str] = field(default_factory=list)
    api_day_count: int = 0


@dataclass
class CacheLoadResult:
    """Cache stream rollup plus optional HTTP 1d MIME mix (``http_mime_1d``) for the cache PDF."""

    rollup: dict[str, Any]
    daily_cache_cf_origin: list[tuple[date, tuple[int | None, int | None]]]
    missing_dates: list[str]
    warnings: list[str] = field(default_factory=list)
    api_day_count: int = 0
    http_mime_1d: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class HttpAdaptiveLoadResult:
    rollup: dict[str, Any]
    missing_dates: list[str]
    warnings: list[str] = field(default_factory=list)
    api_day_count: int = 0


@dataclass
class SnapshotStreamLoadResult:
    """Per-day snapshot streams (DNS records, audit, certificates) rolled up for reporting."""

    rollup: dict[str, Any]
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


def load_http_adaptive_for_range(
    cache_root: Path,
    zone_id: str,
    zone_name: str,
    start: str,
    end: str,
    *,
    top: int,
) -> HttpAdaptiveLoadResult:
    scratch = _load_cached_stream_days(
        cache_root,
        zone_id,
        zone_name,
        start,
        end,
        stream_id="http_adaptive",
        stream_label="HTTP adaptive",
        metric_key="http_requests_analyzed",
    )
    rollup, missing, warns, n_api = _finalize_stream_load(
        scratch, top=top, build_rollup=build_http_adaptive_section
    )
    return HttpAdaptiveLoadResult(
        rollup=rollup,
        missing_dates=missing,
        warnings=warns,
        api_day_count=n_api,
    )


def load_dns_records_for_range(
    cache_root: Path,
    zone_id: str,
    zone_name: str,
    start: str,
    end: str,
    *,
    top: int,
) -> SnapshotStreamLoadResult:
    scratch = _load_cached_stream_days(
        cache_root,
        zone_id,
        zone_name,
        start,
        end,
        stream_id="dns_records",
        stream_label="DNS records",
        metric_key="total_records",
    )
    rollup, missing, warns, n_api = _finalize_stream_load(
        scratch, top=top, build_rollup=build_dns_records_section
    )
    return SnapshotStreamLoadResult(
        rollup=rollup,
        missing_dates=missing,
        warnings=warns,
        api_day_count=n_api,
    )


def load_audit_for_range(
    cache_root: Path,
    zone_id: str,
    zone_name: str,
    start: str,
    end: str,
    *,
    top: int,
) -> SnapshotStreamLoadResult:
    scratch = _load_cached_stream_days(
        cache_root,
        zone_id,
        zone_name,
        start,
        end,
        stream_id="audit",
        stream_label="Audit",
        metric_key="total_events",
    )
    rollup, missing, warns, n_api = _finalize_stream_load(
        scratch, top=top, build_rollup=build_audit_section
    )
    return SnapshotStreamLoadResult(
        rollup=rollup,
        missing_dates=missing,
        warnings=warns,
        api_day_count=n_api,
    )


def load_certificates_for_range(
    cache_root: Path,
    zone_id: str,
    zone_name: str,
    start: str,
    end: str,
    *,
    top: int,
) -> SnapshotStreamLoadResult:
    scratch = _load_cached_stream_days(
        cache_root,
        zone_id,
        zone_name,
        start,
        end,
        stream_id="certificates",
        stream_label="Certificates",
        metric_key="total_certificate_packs",
    )
    rollup, missing, warns, n_api = _finalize_stream_load(
        scratch, top=top, build_rollup=build_certificates_section
    )
    return SnapshotStreamLoadResult(
        rollup=rollup,
        missing_dates=missing,
        warnings=warns,
        api_day_count=n_api,
    )


def _load_security_days_for_range(
    cache_root: Path,
    zone_id: str,
    zone_name: str,
    start: str,
    end: str,
) -> tuple[
    list[dict[str, Any]],
    list[tuple[date, tuple[int | None, int | None, int | None]]],
    list[str],
    list[str],
]:
    warnings: list[str] = []
    api_days: list[dict[str, Any]] = []
    daily_triple: list[tuple[date, tuple[int | None, int | None, int | None]]] = []
    missing_dates: list[str] = []

    for d in iter_dates_inclusive(parse_ymd(start), parse_ymd(end)):
        ds = format_ymd(d)
        path = day_cache_path(cache_root, zone_id, ds, "security")
        raw = read_day_file(path)
        if not raw:
            warnings.append(f"No security cache for zone {zone_name} on {ds}")
            missing_dates.append(ds)
            daily_triple.append((d, (None, None, None)))
            continue
        src = raw.get("_source")
        if src == "null":
            warnings.append(f"Security for zone {zone_name} on {ds} unavailable (null)")
            missing_dates.append(ds)
            daily_triple.append((d, (None, None, None)))
            continue
        if src == "error":
            warnings.append(f"Security for zone {zone_name} on {ds} failed (cached error)")
            missing_dates.append(ds)
            daily_triple.append((d, (None, None, None)))
            continue
        data = raw.get("data")
        if not isinstance(data, dict):
            warnings.append(f"Security for zone {zone_name} on {ds} has no data object")
            missing_dates.append(ds)
            daily_triple.append((d, (None, None, None)))
            continue

        api_days.append(data)
        if "mitigated_count" in data or "served_cf_count" in data:
            m = int(data.get("mitigated_count") or 0)
            cf = int(data.get("served_cf_count") or 0)
            org = int(data.get("served_origin_count") or 0)
            daily_triple.append((d, (m, cf, org)))
        else:
            daily_triple.append((d, (None, None, None)))

    return api_days, daily_triple, missing_dates, warnings


def load_security_for_range(
    cache_root: Path,
    zone_id: str,
    zone_name: str,
    start: str,
    end: str,
    *,
    top: int,
) -> SecurityLoadResult:
    api_days, dtriple, missing, warns = _load_security_days_for_range(
        cache_root, zone_id, zone_name, start, end
    )
    scratch = _StreamDaysScratch(
        api_days=api_days,
        daily_metric=[],
        missing_dates=missing,
        warnings=warns,
    )
    rollup, missing2, _, n_api = _finalize_stream_load(
        scratch, top=top, build_rollup=build_security_section
    )
    return SecurityLoadResult(
        rollup=rollup,
        daily_security_triple=dtriple,
        missing_dates=missing2,
        warnings=warns,
        api_day_count=n_api,
    )


def _merge_http_mime_1d_for_range(
    http_days: list[dict[str, Any]],
    *,
    top: int,
) -> list[dict[str, Any]]:
    """Merge ``response_content_types`` from HTTP daily payloads (request-weighted bars)."""
    acc: dict[str, int] = {}
    for d in http_days:
        for row in d.get("response_content_types") or []:
            if not isinstance(row, dict):
                continue
            raw = row.get("edgeResponseContentTypeName")
            if raw is None:
                raw = row.get("edgeResponseContentType")
            k = str(raw or "").strip() or "unknown"
            acc[k] = acc.get(k, 0) + int(row.get("requests") or 0)
    total = sum(acc.values())
    if total <= 0:
        return []
    items = sorted(acc.items(), key=lambda x: -x[1])[:top]
    return [
        {
            "content_type": name,
            "count": cnt,
            "percentage": round(100.0 * cnt / total, 1),
        }
        for name, cnt in items
    ]


_CACHE_ORIGIN_FETCH_STATUSES = frozenset({"dynamic", "miss", "bypass"})


def _daily_cache_cf_origin_pair(data: dict[str, Any]) -> tuple[int, int]:
    """Same origin bucket as security eyeball pass (dynamic / miss / bypass)."""
    total = 0
    origin = 0
    for row in data.get("by_cache_status") or []:
        if not isinstance(row, dict):
            continue
        st = str(row.get("value") or "").strip().lower()
        c = int(row.get("count") or 0)
        if not st:
            continue
        total += c
        if st in _CACHE_ORIGIN_FETCH_STATUSES:
            origin += c
    return max(0, total - origin), origin


def _load_cache_days_for_range(
    cache_root: Path,
    zone_id: str,
    zone_name: str,
    start: str,
    end: str,
) -> tuple[
    list[dict[str, Any]],
    list[tuple[date, tuple[int | None, int | None]]],
    list[str],
    list[str],
]:
    warnings: list[str] = []
    api_days: list[dict[str, Any]] = []
    daily_pair: list[tuple[date, tuple[int | None, int | None]]] = []
    missing_dates: list[str] = []

    for d in iter_dates_inclusive(parse_ymd(start), parse_ymd(end)):
        ds = format_ymd(d)
        path = day_cache_path(cache_root, zone_id, ds, "cache")
        raw = read_day_file(path)
        if not raw:
            warnings.append(f"No cache data for zone {zone_name} on {ds}")
            missing_dates.append(ds)
            daily_pair.append((d, (None, None)))
            continue
        src = raw.get("_source")
        if src == "null":
            warnings.append(f"Cache for zone {zone_name} on {ds} unavailable (null)")
            missing_dates.append(ds)
            daily_pair.append((d, (None, None)))
            continue
        if src == "error":
            warnings.append(f"Cache for zone {zone_name} on {ds} failed (cached error)")
            missing_dates.append(ds)
            daily_pair.append((d, (None, None)))
            continue
        data = raw.get("data")
        if not isinstance(data, dict):
            warnings.append(f"Cache for zone {zone_name} on {ds} has no data object")
            missing_dates.append(ds)
            daily_pair.append((d, (None, None)))
            continue

        api_days.append(data)
        cf, org = _daily_cache_cf_origin_pair(data)
        daily_pair.append((d, (cf, org)))

    return api_days, daily_pair, missing_dates, warnings


def load_cache_for_range(
    cache_root: Path,
    zone_id: str,
    zone_name: str,
    start: str,
    end: str,
    *,
    top: int,
) -> CacheLoadResult:
    api_days, dtriple, missing, warns = _load_cache_days_for_range(
        cache_root, zone_id, zone_name, start, end
    )
    scratch = _StreamDaysScratch(
        api_days=api_days,
        daily_metric=[],
        missing_dates=missing,
        warnings=warns,
    )
    rollup, missing2, _, n_api = _finalize_stream_load(
        scratch, top=top, build_rollup=build_cache_section
    )
    http_api_days, _, _, _, _, _, _, _, http_warns = _load_http_days_for_range(
        cache_root, zone_id, zone_name, start, end
    )
    for w in http_warns:
        log.debug("%s", w)
    http_mime_1d = _merge_http_mime_1d_for_range(http_api_days, top=top)
    return CacheLoadResult(
        rollup=rollup,
        daily_cache_cf_origin=dtriple,
        missing_dates=missing2,
        warnings=warns,
        api_day_count=n_api,
        http_mime_1d=http_mime_1d,
    )
