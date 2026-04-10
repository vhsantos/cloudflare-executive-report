"""Cache stream aggregation builder."""

from __future__ import annotations

from typing import Any

from cloudflare_executive_report.common.aggregation_helpers import (
    CACHE_ORIGIN_FETCH_STATUSES,
    cache_served_cf_origin_from_status_rows,
    norm_cache_status,
    pct_of_total,
    top_pct,
)
from cloudflare_executive_report.common.formatting import format_bytes_human, format_count_human


def build_cache_section(
    daily_api_data: list[dict[str, Any]],
    *,
    top: int = 10,
) -> dict[str, Any]:
    """Aggregate cache daily payloads into one report section."""
    status_counts: dict[str, int] = {}
    status_bytes: dict[str, int] = {}
    path_counts: dict[str, int] = {}
    served_cf_total = 0
    served_origin_total = 0

    for day in daily_api_data:
        for row in day.get("by_cache_status") or []:
            if not isinstance(row, dict):
                continue
            key = norm_cache_status(str(row.get("value") or ""))
            if not key:
                continue
            status_counts[key] = status_counts.get(key, 0) + int(row.get("count") or 0)
            status_bytes[key] = status_bytes.get(key, 0) + int(row.get("edgeResponseBytes") or 0)

        for row in day.get("top_path_status") or []:
            if not isinstance(row, dict):
                continue
            path = str(row.get("path") or "").strip()
            if path:
                path_counts[path] = path_counts.get(path, 0) + int(row.get("count") or 0)

        served_cf_day, served_origin_day = cache_served_cf_origin_from_status_rows(day)
        served_cf_total += served_cf_day
        served_origin_total += served_origin_day

    total_requests = sum(status_counts.values())
    total_bytes = sum(status_bytes.values())
    hit_requests = int(status_counts.get("hit") or 0)
    miss_requests = int(status_counts.get("miss") or 0)
    dynamic_requests = int(status_counts.get("dynamic") or 0)

    by_status_items = sorted(status_counts.items(), key=lambda x: -x[1])[:top]
    by_status: list[dict[str, Any]] = []
    for key, count in by_status_items:
        by_status.append(
            {
                "status": key,
                "count": count,
                "bytes": int(status_bytes.get(key) or 0),
                "percentage": pct_of_total(count, total_requests),
            }
        )

    def status_row(key: str, count: int) -> dict[str, Any]:
        return {
            "status": key,
            "count": count,
            "bytes": int(status_bytes.get(key) or 0),
            "percentage": pct_of_total(count, total_requests),
        }

    edge_pairs = sorted(
        ((k, v) for k, v in status_counts.items() if k not in CACHE_ORIGIN_FETCH_STATUSES),
        key=lambda x: -x[1],
    )[:5]
    origin_pairs = sorted(
        ((k, v) for k, v in status_counts.items() if k in CACHE_ORIGIN_FETCH_STATUSES),
        key=lambda x: -x[1],
    )
    by_cache_status_edge = [status_row(k, c) for k, c in edge_pairs]
    by_cache_status_origin = [status_row(k, c) for k, c in origin_pairs]

    return {
        "total_requests_sampled": total_requests,
        "total_requests_sampled_human": format_count_human(total_requests),
        "total_edge_response_bytes": total_bytes,
        "total_edge_response_bytes_human": format_bytes_human(total_bytes),
        "hit_requests": hit_requests,
        "hit_requests_human": format_count_human(hit_requests),
        "miss_requests": miss_requests,
        "miss_requests_human": format_count_human(miss_requests),
        "dynamic_requests": dynamic_requests,
        "dynamic_requests_human": format_count_human(dynamic_requests),
        "cache_hit_ratio": pct_of_total(hit_requests, total_requests),
        "served_cf_count": served_cf_total,
        "served_cf_count_human": format_count_human(served_cf_total),
        "served_origin_count": served_origin_total,
        "served_origin_count_human": format_count_human(served_origin_total),
        "by_cache_status": by_status,
        "by_cache_status_edge": by_cache_status_edge,
        "by_cache_status_origin": by_cache_status_origin,
        "top_paths": top_pct(path_counts, total_requests, top, name_key="path")
        if total_requests > 0
        else [],
    }
