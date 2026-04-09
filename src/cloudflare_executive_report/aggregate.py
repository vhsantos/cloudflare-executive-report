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
from cloudflare_executive_report.fetchers.security import (
    ROLLUP_CHALLENGE_SUBSTRINGS,
    ROLLUP_EXCLUDE_ACTION_PREFIXES,
)
from cloudflare_executive_report.formatting import format_bytes_human, format_count_human


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


def _pct_of_total(count: int, total: int) -> float:
    return round(100.0 * count / total, 1) if total > 0 else 0.0


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
        out.append({name_key: k, "count": c, "percentage": _pct_of_total(c, total)})
    return out


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
    uncached_req = max(0, total_req - cached_req)
    uncached_bytes = max(0, total_bytes - cached_bytes)
    enc_req = sum(int(d.get("encrypted_requests") or 0) for d in daily_api_data)
    page_views = sum(int(d.get("page_views") or 0) for d in daily_api_data)
    uniques = sum(int(d.get("uniques") or 0) for d in daily_api_data)
    daily_unique_vals = [int(d.get("uniques") or 0) for d in daily_api_data]
    max_uniques_single_day = max(daily_unique_vals) if daily_unique_vals else 0

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

    ctype_req: dict[str, int] = {}
    for d in daily_api_data:
        for row in d.get("response_content_types") or []:
            if not isinstance(row, dict):
                continue
            raw = row.get("edgeResponseContentTypeName")
            if raw is None:
                raw = row.get("edgeResponseContentType")
            k = str(raw or "").strip() or "unknown"
            ctype_req[k] = ctype_req.get(k, 0) + int(row.get("requests") or 0)

    cache_hit_ratio = 0.0
    if total_req > 0:
        cache_hit_ratio = round(100.0 * cached_req / total_req, 1)

    top_countries: list[dict[str, Any]] = []
    if total_req > 0 and country_req:
        items = sorted(country_req.items(), key=lambda x: -x[1])[:top]
        for k, c in items:
            cname, code = _country_label_code(k)
            pct = _pct_of_total(c, total_req)
            top_countries.append(
                {
                    "country": cname,
                    "code": code,
                    "requests": c,
                    "percentage": pct,
                }
            )

    ctype_total = sum(ctype_req.values())
    top_response_content_types: list[dict[str, Any]] = []
    if ctype_total > 0 and ctype_req:
        items = sorted(ctype_req.items(), key=lambda x: -x[1])[:top]
        for k, c in items:
            top_response_content_types.append(
                {
                    "content_type": k,
                    "requests": c,
                    "percentage": _pct_of_total(c, ctype_total),
                }
            )

    return {
        "total_requests": total_req,
        "total_requests_human": format_count_human(total_req),
        "cached_requests": cached_req,
        "cached_requests_human": format_count_human(cached_req),
        "uncached_requests": uncached_req,
        "uncached_requests_human": format_count_human(uncached_req),
        "total_bandwidth_bytes": total_bytes,
        "total_bandwidth_human": format_bytes_human(total_bytes),
        "cached_bandwidth_bytes": cached_bytes,
        "cached_bandwidth_human": format_bytes_human(cached_bytes),
        "uncached_bandwidth_bytes": uncached_bytes,
        "uncached_bandwidth_human": format_bytes_human(uncached_bytes),
        "unique_visitors": uniques,
        "unique_visitors_human": format_count_human(uniques),
        "max_uniques_single_day": max_uniques_single_day,
        "max_uniques_single_day_human": format_count_human(max_uniques_single_day),
        "cache_hit_ratio": cache_hit_ratio,
        # Same as cached_bandwidth_* (dashboard "bytes saved" / cached egress).
        "cached_bytes_saved": cached_bytes,
        "cached_bytes_saved_human": format_bytes_human(cached_bytes),
        "encrypted_requests": enc_req,
        "encrypted_requests_human": format_count_human(enc_req),
        "page_views": page_views,
        "page_views_human": format_count_human(page_views),
        "top_countries": top_countries,
        "top_response_content_types": top_response_content_types,
    }


def build_http_adaptive_section(
    daily_api_data: list[dict[str, Any]],
    *,
    top: int = 10,
) -> dict[str, Any]:
    total = sum(int(d.get("http_requests_analyzed") or 0) for d in daily_api_data)
    c4 = sum(int(d.get("status_4xx_count") or 0) for d in daily_api_data)
    c5 = sum(int(d.get("status_5xx_count") or 0) for d in daily_api_data)

    weighted_p50_num = 0.0
    weighted_p95_num = 0.0
    weighted_origin_avg_num = 0.0
    weighted_den_p50 = 0
    weighted_den_p95 = 0
    weighted_den_origin_avg = 0
    by_status: dict[str, int] = {}
    for d in daily_api_data:
        n = int(d.get("http_requests_analyzed") or 0)
        p50 = d.get("latency_p50_ms")
        p95 = d.get("latency_p95_ms")
        org_avg = d.get("origin_response_duration_avg_ms")
        if p50 is not None and n > 0:
            weighted_p50_num += float(p50) * n
            weighted_den_p50 += n
        if p95 is not None and n > 0:
            weighted_p95_num += float(p95) * n
            weighted_den_p95 += n
        if org_avg is not None and n > 0:
            weighted_origin_avg_num += float(org_avg) * n
            weighted_den_origin_avg += n
        for row in d.get("by_edge_status") or []:
            if not isinstance(row, dict):
                continue
            st = str(row.get("value") or "").strip()
            if not st:
                continue
            by_status[st] = by_status.get(st, 0) + int(row.get("count") or 0)

    out: dict[str, Any] = {
        "http_requests_analyzed": total,
        "http_requests_analyzed_human": format_count_human(total),
        "status_4xx_count": c4,
        "status_4xx_count_human": format_count_human(c4),
        "status_5xx_count": c5,
        "status_5xx_count_human": format_count_human(c5),
        "status_4xx_rate_pct": _pct_of_total(c4, total) if total > 0 else 0.0,
        "status_5xx_rate_pct": _pct_of_total(c5, total) if total > 0 else 0.0,
        "by_edge_status": _top_pct(by_status, total, top, name_key="status") if total > 0 else [],
    }
    if weighted_den_p50 > 0:
        out["latency_p50_ms"] = round(weighted_p50_num / weighted_den_p50, 2)
    if weighted_den_p95 > 0:
        out["latency_p95_ms"] = round(weighted_p95_num / weighted_den_p95, 2)
    if weighted_den_origin_avg > 0:
        out["origin_response_duration_avg_ms"] = round(
            weighted_origin_avg_num / weighted_den_origin_avg, 2
        )
        # Unweighted mean of per-day averages (differs when daily traffic volume varies).
        daily_avgs = [
            float(d["origin_response_duration_avg_ms"])
            for d in daily_api_data
            if d.get("origin_response_duration_avg_ms") is not None
        ]
        if daily_avgs:
            out["origin_response_duration_avg_ms_daily_mean"] = round(
                sum(daily_avgs) / len(daily_avgs), 2
            )
    return out


def _latest_snapshot_day(
    daily_api_data: list[dict[str, Any]],
) -> dict[str, Any] | None:
    latest: tuple[str, dict[str, Any]] | None = None
    for d in daily_api_data:
        ds = str(d.get("date") or "")
        if not ds:
            continue
        if latest is None or ds > latest[0]:
            latest = (ds, d)
    return latest[1] if latest else (daily_api_data[-1] if daily_api_data else None)


def build_dns_records_section(
    daily_api_data: list[dict[str, Any]],
    *,
    top: int = 10,
) -> dict[str, Any]:
    snap = _latest_snapshot_day(daily_api_data)
    if not isinstance(snap, dict):
        return {}
    if snap.get("unavailable"):
        return {
            "unavailable": True,
            "reason": str(snap.get("reason") or "unknown"),
        }
    rows = list(snap.get("record_types") or [])[:top]
    return {
        "total_records": int(snap.get("total_records") or 0),
        "proxied_records": int(snap.get("proxied_records") or 0),
        "dns_only_records": int(snap.get("dns_only_records") or 0),
        "apex_unproxied_a_aaaa": int(snap.get("apex_unproxied_a_aaaa") or 0),
        "record_types": rows,
    }


def _merge_value_count_rows(
    days: list[dict[str, Any]], key: str, *, top: int
) -> list[dict[str, Any]]:
    acc: dict[str, int] = {}
    for d in days:
        if not isinstance(d, dict) or d.get("unavailable"):
            continue
        for row in d.get(key) or []:
            if not isinstance(row, dict):
                continue
            v = str(row.get("value") or "").strip()
            if not v:
                continue
            acc[v] = acc.get(v, 0) + int(row.get("count") or 0)
    ranked = sorted(acc.items(), key=lambda x: -x[1])[:top]
    return [{"value": k, "count": c} for k, c in ranked]


def build_audit_section(
    daily_api_data: list[dict[str, Any]],
    *,
    top: int = 10,
) -> dict[str, Any]:
    if not daily_api_data:
        return {}
    days_ok = [d for d in daily_api_data if isinstance(d, dict) and not d.get("unavailable")]
    days_un = [d for d in daily_api_data if isinstance(d, dict) and d.get("unavailable")]
    if not days_ok and days_un:
        return {
            "unavailable": True,
            "reason": str(days_un[0].get("reason") or "unknown"),
        }
    total_events = sum(int(d.get("total_events") or 0) for d in days_ok)
    return {
        "total_events": total_events,
        "top_actions": _merge_value_count_rows(daily_api_data, "top_actions", top=top),
        "top_actors": _merge_value_count_rows(daily_api_data, "top_actors", top=top),
    }


def build_certificates_section(
    daily_api_data: list[dict[str, Any]],
    *,
    top: int = 10,
) -> dict[str, Any]:
    snap = _latest_snapshot_day(daily_api_data)
    if not isinstance(snap, dict):
        return {}
    if snap.get("unavailable"):
        return {
            "unavailable": True,
            "reason": str(snap.get("reason") or "unknown"),
        }
    return {
        "total_certificate_packs": int(snap.get("total_certificate_packs") or 0),
        "expiring_in_30_days": int(snap.get("expiring_in_30_days") or 0),
        "soonest_expiry": snap.get("soonest_expiry"),
        "status_breakdown": list(snap.get("status_breakdown") or [])[:top],
    }


def _norm_cache_status(raw: str) -> str:
    return raw.strip().lower()


# Same origin bucket as security pass traffic (dynamic / miss / bypass).
_CACHE_ORIGIN_FETCH_STATUSES = frozenset({"dynamic", "miss", "bypass"})


def _cache_served_cf_origin_from_status_rows(day: dict[str, Any]) -> tuple[int, int]:
    """Return (served_cf_requests, served_origin_requests) from marginal cache status counts."""
    total = 0
    origin = 0
    for row in day.get("by_cache_status") or []:
        if not isinstance(row, dict):
            continue
        st = _norm_cache_status(str(row.get("value") or ""))
        c = int(row.get("count") or 0)
        if not st:
            continue
        total += c
        if st in _CACHE_ORIGIN_FETCH_STATUSES:
            origin += c
    served_cf = max(0, total - origin)
    return served_cf, origin


def _cache_status_counts(day: dict[str, Any]) -> dict[str, int]:
    out: dict[str, int] = {}
    for row in day.get("by_cache_status") or []:
        if not isinstance(row, dict):
            continue
        status = _norm_cache_status(str(row.get("value") or ""))
        if not status:
            continue
        out[status] = out.get(status, 0) + int(row.get("count") or 0)
    return out


def build_cache_section(
    daily_api_data: list[dict[str, Any]],
    *,
    top: int = 10,
) -> dict[str, Any]:
    status_counts: dict[str, int] = {}
    status_bytes: dict[str, int] = {}
    path_counts: dict[str, int] = {}
    served_cf_total = 0
    served_origin_total = 0

    for d in daily_api_data:
        for row in d.get("by_cache_status") or []:
            if not isinstance(row, dict):
                continue
            k = _norm_cache_status(str(row.get("value") or ""))
            if not k:
                continue
            status_counts[k] = status_counts.get(k, 0) + int(row.get("count") or 0)
            status_bytes[k] = status_bytes.get(k, 0) + int(row.get("edgeResponseBytes") or 0)

        for row in d.get("top_path_status") or []:
            if not isinstance(row, dict):
                continue
            p = str(row.get("path") or "").strip()
            if p:
                path_counts[p] = path_counts.get(p, 0) + int(row.get("count") or 0)

        cf_d, org_d = _cache_served_cf_origin_from_status_rows(d)
        served_cf_total += cf_d
        served_origin_total += org_d

    total_requests = sum(status_counts.values())
    total_bytes = sum(status_bytes.values())
    hit = int(status_counts.get("hit") or 0)
    miss = int(status_counts.get("miss") or 0)
    dynamic = int(status_counts.get("dynamic") or 0)

    by_status_items = sorted(status_counts.items(), key=lambda x: -x[1])[:top]
    by_status: list[dict[str, Any]] = []
    for k, c in by_status_items:
        by_status.append(
            {
                "status": k,
                "count": c,
                "bytes": int(status_bytes.get(k) or 0),
                "percentage": _pct_of_total(c, total_requests),
            }
        )

    return {
        "total_requests_sampled": total_requests,
        "total_requests_sampled_human": format_count_human(total_requests),
        "total_edge_response_bytes": total_bytes,
        "total_edge_response_bytes_human": format_bytes_human(total_bytes),
        "hit_requests": hit,
        "hit_requests_human": format_count_human(hit),
        "miss_requests": miss,
        "miss_requests_human": format_count_human(miss),
        "dynamic_requests": dynamic,
        "dynamic_requests_human": format_count_human(dynamic),
        "cache_hit_ratio": _pct_of_total(hit, total_requests),
        "served_cf_count": served_cf_total,
        "served_cf_count_human": format_count_human(served_cf_total),
        "served_origin_count": served_origin_total,
        "served_origin_count_human": format_count_human(served_origin_total),
        "by_cache_status": by_status,
        "top_paths": _top_pct(path_counts, total_requests, top, name_key="path")
        if total_requests > 0
        else [],
    }


def _security_normalize_day(d: dict[str, Any]) -> dict[str, Any]:
    out = dict(d)
    if out.get("by_action") is None:
        out["by_action"] = []
    return out


def _security_merge_ip_buckets(days: list[dict[str, Any]], *, top: int) -> list[dict[str, Any]]:
    m: dict[tuple[str, str], int] = {}
    for d in days:
        rows = d.get("attack_source_buckets")
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            ip = str(row.get("ip") or "").strip()
            if not ip:
                continue
            key = (ip, str(row.get("country") or "").strip())
            m[key] = m.get(key, 0) + int(row.get("count") or 0)
    if not m:
        return []
    tot = sum(m.values())
    items = sorted(m.items(), key=lambda x: -x[1])[:top]
    return [
        {
            "ip": k[0],
            "country": k[1],
            "count": c,
            "percentage": _pct_of_total(c, tot),
        }
        for k, c in items
    ]


def _security_top_countries(country_counts: dict[str, int], *, top: int) -> list[dict[str, Any]]:
    if not country_counts:
        return []
    total = sum(country_counts.values())
    items = sorted(country_counts.items(), key=lambda x: -x[1])[:top]
    out: list[dict[str, Any]] = []
    for k, c in items:
        cname, code = _country_label_code(k)
        out.append(
            {
                "country": cname,
                "code": code,
                "count": c,
                "requests": c,
                "percentage": _pct_of_total(c, total),
            }
        )
    return out


def _security_among_mitigated(by_action: dict[str, int]) -> dict[str, int]:
    out: dict[str, int] = {}
    for k, c in by_action.items():
        kl = k.lower()
        if kl == "log":
            continue
        if any(k.startswith(p) for p in ROLLUP_EXCLUDE_ACTION_PREFIXES):
            continue
        out[k] = c
    return out


def _security_challenge_and_block(by_action: dict[str, int]) -> tuple[int, int]:
    ch = blk = 0
    for k, c in by_action.items():
        kl = k.lower()
        if kl == "block":
            blk += c
        elif any(s in kl for s in ROLLUP_CHALLENGE_SUBSTRINGS):
            ch += c
    return ch, blk


def _security_timeseries(days: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for d in days:
        ds = d.get("date")
        if not ds:
            continue
        rows.append(
            {
                "date": str(ds),
                "http_requests_sampled": int(d.get("http_requests_sampled") or 0),
                "mitigated_count": int(d.get("mitigated_count") or 0),
                "served_cf_count": int(d.get("served_cf_count") or 0),
                "served_origin_count": int(d.get("served_origin_count") or 0),
            }
        )
    return rows


def _security_coalesce_http_sampled(
    days: list[dict[str, Any]],
    mitigated: int,
    served_cf: int,
    served_origin: int,
) -> int:
    """Prefer summed daily ``http_requests_sampled``; if absent/zero, use matrix components."""
    http_sampled = sum(int(d.get("http_requests_sampled") or 0) for d in days)
    if http_sampled > 0:
        return http_sampled
    inferred = mitigated + served_cf + served_origin
    return inferred if inferred > 0 else 0


def build_security_section(
    daily_api_data: list[dict[str, Any]],
    *,
    top: int = 10,
) -> dict[str, Any]:
    """Roll up ``security.json`` ``data`` objects (same shape as DNS/HTTP daily lists)."""
    days = [_security_normalize_day(d) for d in daily_api_data]
    by_action = _merge_rows(days, "by_action")
    action_total = sum(by_action.values())

    mitigated = sum(int(d.get("mitigated_count") or 0) for d in days)
    served_cf = sum(int(d.get("served_cf_count") or 0) for d in days)
    served_origin = sum(int(d.get("served_origin_count") or 0) for d in days)
    http_sampled = _security_coalesce_http_sampled(days, mitigated, served_cf, served_origin)
    not_mitigated = served_cf + served_origin

    among = _security_among_mitigated(by_action)
    among_total = sum(among.values())
    ch_n, blk_n = _security_challenge_and_block(by_action)

    by_source = _merge_rows(days, "by_source")
    src_total = sum(by_source.values())
    ip_top = max(top, 20)

    cache_merged = _merge_rows(days, "http_by_cache_status")
    cache_total = sum(cache_merged.values())
    method_merged = _merge_rows(days, "by_http_method")
    method_total = sum(method_merged.values())
    path_merged = _merge_rows(days, "by_attack_path")
    path_total = sum(path_merged.values())
    country_merged = _merge_rows(days, "by_attack_country")

    mitigation_rate = _pct_of_total(mitigated, http_sampled) if http_sampled else 0.0

    out: dict[str, Any] = {
        "total_events": action_total,
        "total_events_human": format_count_human(action_total),
        "top_actions": _top_pct(by_action, action_total, top, name_key="action"),
        "timeseries_daily": _security_timeseries(days),
        "top_attack_sources": _security_merge_ip_buckets(days, top=ip_top),
        "top_source_countries": _security_top_countries(country_merged, top=ip_top),
        "cache_status_breakdown": _top_pct(cache_merged, cache_total, top, name_key="status")
        if cache_total > 0
        else [],
        "http_methods_breakdown": _top_pct(method_merged, method_total, top, name_key="method")
        if method_total > 0
        else [],
        "top_attack_paths": _top_pct(path_merged, path_total, top, name_key="path")
        if path_total > 0
        else [],
    }
    if http_sampled > 0:
        out["http_requests_sampled"] = http_sampled
        out["http_requests_sampled_human"] = format_count_human(http_sampled)
        out["mitigated_count"] = mitigated
        out["mitigated_count_human"] = format_count_human(mitigated)
        out["not_mitigated_sampled"] = not_mitigated
        out["not_mitigated_sampled_human"] = format_count_human(not_mitigated)
        out["mitigation_rate_pct"] = mitigation_rate
        out["served_cf_count"] = served_cf
        out["served_cf_count_human"] = format_count_human(served_cf)
        out["served_origin_count"] = served_origin
        out["served_origin_count_human"] = format_count_human(served_origin)
        out["challenge_events_sampled"] = ch_n
        out["challenge_events_sampled_human"] = format_count_human(ch_n)
        out["block_events_sampled"] = blk_n
        out["block_events_sampled_human"] = format_count_human(blk_n)
    if among_total > 0:
        out["actions_among_mitigated"] = _top_pct(among, among_total, top, name_key="action")
    out["top_security_services"] = (
        _top_pct(by_source, src_total, top, name_key="service") if src_total > 0 else []
    )
    return out


SectionBuilder = Callable[..., dict[str, Any]]

SECTION_BUILDERS: dict[str, SectionBuilder] = {
    "dns": build_dns_section,
    "http": build_http_section,
    "http_adaptive": build_http_adaptive_section,
    "security": build_security_section,
    "cache": build_cache_section,
    "dns_records": build_dns_records_section,
    "audit": build_audit_section,
    "certificates": build_certificates_section,
}


def build_report(
    *,
    zones_out: list[dict[str, Any]],
    warnings: list[str],
    period_start: str,
    period_end: str,
    requested_start: str,
    requested_end: str,
    report_type: str,
    data_fingerprint: dict[str, Any] | None = None,
    zone_health_fetched_at: str | None = None,
) -> dict[str, Any]:
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    out = {
        "report_period": {
            "start": period_start,
            "end": period_end,
            "timezone": "UTC",
            "requested_start": requested_start,
            "requested_end": requested_end,
        },
        "generated_at": now,
        "tool_version": __version__,
        "report_type": str(report_type),
        "zones": zones_out,
        "warnings": warnings,
    }
    if data_fingerprint is not None:
        out["data_fingerprint"] = data_fingerprint
    out["zone_health_fetched_at"] = str(zone_health_fetched_at or now)
    return out


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
            warnings.append(f"{label} for zone {zone_name} on {ds} unavailable (cache miss)")
            continue
        src = raw.get("_source")
        if src == "null":
            warnings.append(f"{label} for zone {zone_name} on {ds} unavailable (cached null)")
            continue
        if src == "error":
            warnings.append(f"{label} for zone {zone_name} on {ds} failed (cached error)")
            continue
        data = raw.get("data")
        if isinstance(data, dict):
            api_days.append(data)
        else:
            warnings.append(
                f"{label} for zone {zone_name} on {ds} unavailable "
                "(cached entry has no data object)"
            )
    return api_days, warnings
