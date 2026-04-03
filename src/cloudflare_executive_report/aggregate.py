"""Build report JSON from cached daily payloads."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pycountry

from cloudflare_executive_report import __version__
from cloudflare_executive_report.dates import (
    format_ymd,
    iter_dates_inclusive,
    parse_ymd,
)


def _merge_rows(
    days: list[dict[str, Any]],
    key: str,
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for day in days:
        for row in day.get(key) or []:
            if not isinstance(row, dict):
                continue
            v = row.get("value")
            if v is None:
                continue
            c = int(row.get("count") or 0)
            counts[str(v)] = counts.get(str(v), 0) + c
    return counts


def _top_pct(
    counts: dict[str, int],
    total: int,
    top: int,
    *,
    name_key: str,
) -> list[dict[str, Any]]:
    if total <= 0:
        return []
    items = sorted(counts.items(), key=lambda x: -x[1])[:top]
    out: list[dict[str, Any]] = []
    for k, c in items:
        pct = round(100.0 * c / total, 1)
        out.append({name_key: k, "count": c, "percentage": pct})
    return out


def format_bytes_human(n: int) -> str:
    if n < 0:
        n = 0
    units = ("B", "KB", "MB", "GB", "TB")
    v = float(n)
    u = 0
    while v >= 1024 and u < len(units) - 1:
        v /= 1024.0
        u += 1
    if u == 0:
        return f"{int(v)} B"
    return f"{v:.1f} {units[u]}"


def format_count_human(n: int) -> str:
    if n < 0:
        n = 0
    if n < 1000:
        return str(n)
    if n < 1_000_000:
        v = n / 1000.0
        s = f"{v:.1f}".rstrip("0").rstrip(".")
        return f"{s}K"
    if n < 1_000_000_000:
        v = n / 1_000_000.0
        s = f"{v:.1f}".rstrip("0").rstrip(".")
        return f"{s}M"
    v = n / 1_000_000_000.0
    s = f"{v:.1f}".rstrip("0").rstrip(".")
    return f"{s}B"


def _country_label_code(client_country_name: str) -> tuple[str, str]:
    raw = str(client_country_name).strip()
    if len(raw) == 2 and raw.isalpha():
        code = raw.upper()
        c = pycountry.countries.get(alpha_2=code)
        return (c.name if c else code), code
    try:
        fuzzy = pycountry.countries.search_fuzzy(raw)
        if fuzzy:
            c = fuzzy[0]
            return c.name, c.alpha_2
    except LookupError:
        pass
    return raw, raw[:2].upper() if len(raw) == 2 else "ZZ"


def build_dns_section(
    daily_api_data: list[dict[str, Any]],
    *,
    top: int = 10,
) -> dict[str, Any]:
    """daily_api_data: list of `data` objects from dns.json (_source=api)."""
    total_q = sum(int(d.get("total_queries") or 0) for d in daily_api_data)
    seconds = 86400 * max(len(daily_api_data), 1)
    avg_qps = round(total_q / seconds, 3) if seconds else 0.0

    w_num = 0.0
    w_den = 0
    for d in daily_api_data:
        tq = int(d.get("total_queries") or 0)
        apt = d.get("avg_processing_time_us")
        if tq > 0 and apt is not None:
            w_num += float(apt) * tq
            w_den += tq
    avg_ms = None
    if w_den > 0:
        avg_ms = round(w_num / w_den / 1000.0, 3)

    by_name = _merge_rows(daily_api_data, "by_query_name")
    by_type = _merge_rows(daily_api_data, "by_query_type")
    by_rc = _merge_rows(daily_api_data, "by_response_code")
    by_colo = _merge_rows(daily_api_data, "by_colo")
    by_proto = _merge_rows(daily_api_data, "by_protocol")
    by_ver = _merge_rows(daily_api_data, "by_ip_version")

    top_colo = _top_pct(by_colo, total_q, top, name_key="colo")

    def norm_version(v: str) -> str:
        if v in ("4", "ipv4", "IPv4"):
            return "IPv4"
        if v in ("6", "ipv6", "IPv6"):
            return "IPv6"
        return v

    ip_versions_m: dict[str, int] = {}
    for k, c in by_ver.items():
        ip_versions_m[norm_version(k)] = ip_versions_m.get(norm_version(k), 0) + c

    dns: dict[str, Any] = {
        "total_queries": total_q,
        "average_qps": avg_qps,
        "top_query_names": _top_pct(by_name, total_q, top, name_key="name"),
        "top_record_types": _top_pct(by_type, total_q, top, name_key="type"),
        "response_codes": _top_pct(by_rc, total_q, top, name_key="code"),
        "top_data_centers": top_colo,
        "protocols": _top_pct(by_proto, total_q, top, name_key="protocol"),
        "ip_versions": _top_pct(ip_versions_m, total_q, top, name_key="version"),
    }
    if avg_ms is not None:
        dns["average_processing_time_ms"] = avg_ms
    return dns


def build_http_section(
    daily_api_data: list[dict[str, Any]],
    *,
    top: int = 10,
) -> dict[str, Any]:
    total_req = sum(int(d.get("requests") or 0) for d in daily_api_data)
    total_bytes = sum(int(d.get("bytes") or 0) for d in daily_api_data)
    cached_req = sum(int(d.get("cached_requests") or 0) for d in daily_api_data)
    cached_bytes = sum(int(d.get("cached_bytes") or 0) for d in daily_api_data)
    enc_req = sum(int(d.get("encrypted_requests") or 0) for d in daily_api_data)
    page_views = sum(int(d.get("page_views") or 0) for d in daily_api_data)
    uniques = sum(int(d.get("uniques") or 0) for d in daily_api_data)

    country_req: dict[str, int] = {}
    for d in daily_api_data:
        for row in d.get("country_map") or []:
            if not isinstance(row, dict):
                continue
            name = row.get("clientCountryName")
            if name is None:
                continue
            k = str(name)
            country_req[k] = country_req.get(k, 0) + int(row.get("requests") or 0)

    cache_hit_ratio = 0.0
    if total_req > 0:
        cache_hit_ratio = round(100.0 * cached_req / total_req, 1)

    top_countries: list[dict[str, Any]] = []
    if total_req > 0 and country_req:
        items = sorted(country_req.items(), key=lambda x: -x[1])[:top]
        for k, c in items:
            cname, code = _country_label_code(k)
            pct = round(100.0 * c / total_req, 1)
            top_countries.append(
                {
                    "country": cname,
                    "code": code,
                    "requests": c,
                    "percentage": pct,
                }
            )

    return {
        "total_requests": total_req,
        "total_requests_human": format_count_human(total_req),
        "total_bandwidth_bytes": total_bytes,
        "total_bandwidth_human": format_bytes_human(total_bytes),
        "unique_visitors": uniques,
        "unique_visitors_human": format_count_human(uniques),
        "cache_hit_ratio": cache_hit_ratio,
        "cached_requests": cached_req,
        "cached_bytes_saved": cached_bytes,
        "cached_bytes_saved_human": format_bytes_human(cached_bytes),
        "encrypted_requests": enc_req,
        "page_views": page_views,
        "page_views_human": format_count_human(page_views),
        "top_countries": top_countries,
    }


SectionBuilder = Callable[..., dict[str, Any]]

SECTION_BUILDERS: dict[str, SectionBuilder] = {
    "dns": build_dns_section,
    "http": build_http_section,
}


def build_report(
    *,
    zones_out: list[dict[str, Any]],
    warnings: list[str],
    period_start: str,
    period_end: str,
    requested_start: str,
    requested_end: str,
) -> dict[str, Any]:
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "report_period": {
            "start": period_start,
            "end": period_end,
            "timezone": "UTC",
            "requested_start": requested_start,
            "requested_end": requested_end,
        },
        "generated_at": now,
        "tool_version": __version__,
        "zones": zones_out,
        "warnings": warnings,
    }


def collect_days_payloads(
    cache_read_fn: Any,
    zone_id: str,
    zone_name: str,
    start: str,
    end: str,
    *,
    label: str = "DNS",
) -> tuple[list[dict[str, Any]], list[str]]:
    """
    Read one cache file per day; return (api data list, warnings).
    Skips error/null days for aggregation (warnings added).
    """
    warnings: list[str] = []
    api_days: list[dict[str, Any]] = []
    s, e = parse_ymd(start), parse_ymd(end)
    for d in iter_dates_inclusive(s, e):
        ds = format_ymd(d)
        raw = cache_read_fn(zone_id, ds)
        if not raw:
            warnings.append(f"No {label} cache entry for zone {zone_name} on {ds}")
            continue
        src = raw.get("_source")
        if src == "null":
            warnings.append(
                f"{label} data for zone {zone_name} on {ds} is unavailable "
                "(outside retention or not exposed for this plan)"
            )
            continue
        if src == "error":
            warnings.append(f"{label} data for zone {zone_name} on {ds} failed (cached error)")
            continue
        data = raw.get("data")
        if isinstance(data, dict):
            api_days.append(data)
    return api_days, warnings
