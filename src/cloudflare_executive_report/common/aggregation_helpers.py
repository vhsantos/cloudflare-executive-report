"""Shared helpers for stream aggregation builders."""

from __future__ import annotations

from typing import Any

import pycountry

from cloudflare_executive_report.fetchers.security import (
    ROLLUP_CHALLENGE_SUBSTRINGS,
    ROLLUP_EXCLUDE_ACTION_PREFIXES,
)

# Same origin bucket as security pass traffic (dynamic / miss / bypass).
CACHE_ORIGIN_FETCH_STATUSES = frozenset({"dynamic", "miss", "bypass"})


def merge_rows(days: list[dict[str, Any]], key: str) -> dict[str, int]:
    """Merge value/count row lists across days into a single count map."""
    counts: dict[str, int] = {}
    for day in days:
        for row in day.get(key) or []:
            if not isinstance(row, dict):
                continue
            value = row.get("value")
            if value is None:
                continue
            count = int(row.get("count") or 0)
            counts[str(value)] = counts.get(str(value), 0) + count
    return counts


def pct_of_total(count: int, total: int) -> float:
    """Return percentage with one decimal, safe for zero totals."""
    return round(100.0 * count / total, 1) if total > 0 else 0.0


def top_pct(
    counts: dict[str, int],
    total: int,
    top: int,
    *,
    name_key: str,
) -> list[dict[str, Any]]:
    """Return ranked top rows with percentage field."""
    if total <= 0:
        return []
    items = sorted(counts.items(), key=lambda x: -x[1])[:top]
    out: list[dict[str, Any]] = []
    for key, count in items:
        out.append({name_key: key, "count": count, "percentage": pct_of_total(count, total)})
    return out


def country_label_code(client_country_name: str) -> tuple[str, str]:
    """Normalize country input to display name and 2-letter code."""
    raw = str(client_country_name).strip()
    if len(raw) == 2 and raw.isalpha():
        code = raw.upper()
        country = pycountry.countries.get(alpha_2=code)
        return (country.name if country else code), code
    try:
        fuzzy = pycountry.countries.search_fuzzy(raw)
        if fuzzy:
            country = fuzzy[0]
            name = getattr(country, "name", raw)
            code = getattr(country, "alpha_2", "ZZ")
            return str(name), str(code)
    except LookupError:
        pass
    return raw, raw[:2].upper() if len(raw) == 2 else "ZZ"


def latest_snapshot_day(daily_api_data: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Return latest day by date field, with fallback to final list item."""
    latest: tuple[str, dict[str, Any]] | None = None
    for day in daily_api_data:
        day_string = str(day.get("date") or "")
        if not day_string:
            continue
        if latest is None or day_string > latest[0]:
            latest = (day_string, day)
    return latest[1] if latest else (daily_api_data[-1] if daily_api_data else None)


def merge_value_count_rows(
    days: list[dict[str, Any]],
    key: str,
    *,
    top: int,
) -> list[dict[str, Any]]:
    """Merge rows shaped as {value,count} across days and return ranked output."""
    merged: dict[str, int] = {}
    for day in days:
        if not isinstance(day, dict) or day.get("unavailable"):
            continue
        for row in day.get(key) or []:
            if not isinstance(row, dict):
                continue
            value = str(row.get("value") or "").strip()
            if not value:
                continue
            merged[value] = merged.get(value, 0) + int(row.get("count") or 0)
    ranked = sorted(merged.items(), key=lambda x: -x[1])[:top]
    return [{"value": key, "count": count} for key, count in ranked]


def norm_cache_status(raw: str) -> str:
    """Normalize cache status token for rollups."""
    return raw.strip().lower()


def cache_served_cf_origin_from_status_rows(day: dict[str, Any]) -> tuple[int, int]:
    """Return (served_cf_requests, served_origin_requests) from cache status rows."""
    total = 0
    origin = 0
    for row in day.get("by_cache_status") or []:
        if not isinstance(row, dict):
            continue
        status = norm_cache_status(str(row.get("value") or ""))
        count = int(row.get("count") or 0)
        if not status:
            continue
        total += count
        if status in CACHE_ORIGIN_FETCH_STATUSES:
            origin += count
    served_cf = max(0, total - origin)
    return served_cf, origin


def security_normalize_day(day: dict[str, Any]) -> dict[str, Any]:
    """Ensure security daily payload has expected keys."""
    out = dict(day)
    if out.get("by_action") is None:
        out["by_action"] = []
    return out


def security_merge_ip_buckets(
    days: list[dict[str, Any]],
    *,
    top: int,
) -> list[dict[str, Any]]:
    """Merge security attack source bucket rows and return ranked output."""
    merged: dict[tuple[str, str], int] = {}
    for day in days:
        rows = day.get("attack_source_buckets")
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            ip = str(row.get("ip") or "").strip()
            if not ip:
                continue
            key = (ip, str(row.get("country") or "").strip())
            merged[key] = merged.get(key, 0) + int(row.get("count") or 0)
    if not merged:
        return []
    total = sum(merged.values())
    items = sorted(merged.items(), key=lambda x: -x[1])[:top]
    return [
        {
            "ip": key[0],
            "country": key[1],
            "count": count,
            "percentage": pct_of_total(count, total),
        }
        for key, count in items
    ]


def security_top_countries(country_counts: dict[str, int], *, top: int) -> list[dict[str, Any]]:
    """Return ranked source country rows for security stream."""
    if not country_counts:
        return []
    total = sum(country_counts.values())
    items = sorted(country_counts.items(), key=lambda x: -x[1])[:top]
    out: list[dict[str, Any]] = []
    for key, count in items:
        country_name, code = country_label_code(key)
        out.append(
            {
                "country": country_name,
                "code": code,
                "count": count,
                "requests": count,
                "percentage": pct_of_total(count, total),
            }
        )
    return out


def security_among_mitigated(by_action: dict[str, int]) -> dict[str, int]:
    """Filter action map to rows that are part of mitigated path."""
    out: dict[str, int] = {}
    for key, count in by_action.items():
        key_lower = key.lower()
        if key_lower == "log":
            continue
        if any(key.startswith(prefix) for prefix in ROLLUP_EXCLUDE_ACTION_PREFIXES):
            continue
        out[key] = count
    return out


def security_challenge_and_block(by_action: dict[str, int]) -> tuple[int, int]:
    """Return challenge and block counts from merged action map."""
    challenge_count = 0
    block_count = 0
    for key, count in by_action.items():
        key_lower = key.lower()
        if key_lower == "block":
            block_count += count
        elif any(token in key_lower for token in ROLLUP_CHALLENGE_SUBSTRINGS):
            challenge_count += count
    return challenge_count, block_count


def security_timeseries(days: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build daily time series rows for security dashboard charts."""
    rows: list[dict[str, Any]] = []
    for day in days:
        day_string = day.get("date")
        if not day_string:
            continue
        rows.append(
            {
                "date": str(day_string),
                "http_requests_sampled": int(day.get("http_requests_sampled") or 0),
                "mitigated_count": int(day.get("mitigated_count") or 0),
                "served_cf_count": int(day.get("served_cf_count") or 0),
                "served_origin_count": int(day.get("served_origin_count") or 0),
            }
        )
    return rows


def security_coalesce_http_sampled(
    days: list[dict[str, Any]],
    mitigated: int,
    served_cf: int,
    served_origin: int,
) -> int:
    """Prefer summed daily sampled count; else infer from matrix components."""
    http_sampled = sum(int(day.get("http_requests_sampled") or 0) for day in days)
    if http_sampled > 0:
        return http_sampled
    inferred = mitigated + served_cf + served_origin
    return inferred if inferred > 0 else 0
