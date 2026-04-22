"""HTTP stream aggregation builder."""

from __future__ import annotations

from typing import Any

from cloudflare_executive_report.common.aggregation_helpers import (
    country_label_code,
    pct_of_total,
)
from cloudflare_executive_report.common.boundary import filter_dict_rows
from cloudflare_executive_report.common.formatting import format_bytes_human, format_count_human


def build_http_section(
    daily_api_data: list[dict[str, Any]],
    *,
    top: int = 10,
) -> dict[str, Any]:
    """Aggregate HTTP daily payloads into one report section."""
    total_requests = sum(int(day.get("requests") or 0) for day in daily_api_data)
    total_bytes = sum(int(day.get("bytes") or 0) for day in daily_api_data)
    cached_requests = sum(int(day.get("cached_requests") or 0) for day in daily_api_data)
    cached_bytes = sum(int(day.get("cached_bytes") or 0) for day in daily_api_data)
    uncached_requests = max(0, total_requests - cached_requests)
    uncached_bytes = max(0, total_bytes - cached_bytes)
    encrypted_requests = sum(int(day.get("encrypted_requests") or 0) for day in daily_api_data)
    page_views = sum(int(day.get("page_views") or 0) for day in daily_api_data)
    uniques = sum(int(day.get("uniques") or 0) for day in daily_api_data)
    daily_unique_values = [int(day.get("uniques") or 0) for day in daily_api_data]
    max_uniques_single_day = max(daily_unique_values) if daily_unique_values else 0

    country_requests: dict[str, int] = {}
    for day in daily_api_data:
        for row in filter_dict_rows(day.get("country_map")):
            country_name = row.get("clientCountryName")
            if country_name is None:
                continue
            key = str(country_name)
            country_requests[key] = country_requests.get(key, 0) + int(row.get("requests") or 0)

    content_type_requests: dict[str, int] = {}
    for day in daily_api_data:
        for row in filter_dict_rows(day.get("response_content_types")):
            raw = row.get("edgeResponseContentTypeName")
            if raw is None:
                raw = row.get("edgeResponseContentType")
            key = str(raw or "").strip() or "unknown"
            content_type_requests[key] = content_type_requests.get(key, 0) + int(
                row.get("requests") or 0
            )

    cache_hit_ratio = 0.0
    if total_requests > 0:
        cache_hit_ratio = round(100.0 * cached_requests / total_requests, 1)

    top_countries: list[dict[str, Any]] = []
    if total_requests > 0 and country_requests:
        items = sorted(country_requests.items(), key=lambda x: -x[1])[:top]
        for key, count in items:
            country_name, code = country_label_code(key)
            top_countries.append(
                {
                    "country": country_name,
                    "code": code,
                    "requests": count,
                    "percentage": pct_of_total(count, total_requests),
                }
            )

    content_type_total = sum(content_type_requests.values())
    top_response_content_types: list[dict[str, Any]] = []
    if content_type_total > 0 and content_type_requests:
        items = sorted(content_type_requests.items(), key=lambda x: -x[1])[:top]
        for key, count in items:
            top_response_content_types.append(
                {
                    "content_type": key,
                    "requests": count,
                    "percentage": pct_of_total(count, content_type_total),
                }
            )

    return {
        "total_requests": total_requests,
        "total_requests_human": format_count_human(total_requests),
        "cached_requests": cached_requests,
        "cached_requests_human": format_count_human(cached_requests),
        "uncached_requests": uncached_requests,
        "uncached_requests_human": format_count_human(uncached_requests),
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
        "cached_bytes_saved": cached_bytes,
        "cached_bytes_saved_human": format_bytes_human(cached_bytes),
        "encrypted_requests": encrypted_requests,
        "encrypted_requests_human": format_count_human(encrypted_requests),
        "page_views": page_views,
        "page_views_human": format_count_human(page_views),
        "top_countries": top_countries,
        "top_response_content_types": top_response_content_types,
    }
