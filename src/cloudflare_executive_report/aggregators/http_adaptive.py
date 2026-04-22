"""HTTP adaptive stream aggregation builder."""

from __future__ import annotations

from typing import Any

from cloudflare_executive_report.common.aggregation_helpers import pct_of_total, top_pct
from cloudflare_executive_report.common.boundary import filter_dict_rows
from cloudflare_executive_report.common.formatting import format_count_human


def build_http_adaptive_section(
    daily_api_data: list[dict[str, Any]],
    *,
    top: int = 10,
) -> dict[str, Any]:
    """Aggregate HTTP adaptive daily payloads into one report section."""
    total = sum(int(day.get("http_requests_analyzed") or 0) for day in daily_api_data)
    count_4xx = sum(int(day.get("status_4xx_count") or 0) for day in daily_api_data)
    count_5xx = sum(int(day.get("status_5xx_count") or 0) for day in daily_api_data)

    weighted_p50_num = 0.0
    weighted_p95_num = 0.0
    weighted_origin_avg_num = 0.0
    weighted_den_p50 = 0
    weighted_den_p95 = 0
    weighted_den_origin_avg = 0
    by_status: dict[str, int] = {}
    for day in daily_api_data:
        sample_count = int(day.get("http_requests_analyzed") or 0)
        p50 = day.get("latency_p50_ms")
        p95 = day.get("latency_p95_ms")
        origin_avg = day.get("origin_response_duration_avg_ms")
        if p50 is not None and sample_count > 0:
            weighted_p50_num += float(p50) * sample_count
            weighted_den_p50 += sample_count
        if p95 is not None and sample_count > 0:
            weighted_p95_num += float(p95) * sample_count
            weighted_den_p95 += sample_count
        if origin_avg is not None and sample_count > 0:
            weighted_origin_avg_num += float(origin_avg) * sample_count
            weighted_den_origin_avg += sample_count
        for row in filter_dict_rows(day.get("by_edge_status")):
            status = str(row.get("value") or "").strip()
            if not status:
                continue
            by_status[status] = by_status.get(status, 0) + int(row.get("count") or 0)

    out: dict[str, Any] = {
        "http_requests_analyzed": total,
        "http_requests_analyzed_human": format_count_human(total),
        "status_4xx_count": count_4xx,
        "status_4xx_count_human": format_count_human(count_4xx),
        "status_5xx_count": count_5xx,
        "status_5xx_count_human": format_count_human(count_5xx),
        "status_4xx_rate_pct": pct_of_total(count_4xx, total) if total > 0 else 0.0,
        "status_5xx_rate_pct": pct_of_total(count_5xx, total) if total > 0 else 0.0,
        "by_edge_status": top_pct(by_status, total, top, name_key="status") if total > 0 else [],
    }
    if weighted_den_p50 > 0:
        out["latency_p50_ms"] = round(weighted_p50_num / weighted_den_p50, 2)
    if weighted_den_p95 > 0:
        out["latency_p95_ms"] = round(weighted_p95_num / weighted_den_p95, 2)
    if weighted_den_origin_avg > 0:
        out["origin_response_duration_avg_ms"] = round(
            weighted_origin_avg_num / weighted_den_origin_avg, 2
        )
        daily_avgs = [
            float(day["origin_response_duration_avg_ms"])
            for day in daily_api_data
            if day.get("origin_response_duration_avg_ms") is not None
        ]
        if daily_avgs:
            out["origin_response_duration_avg_ms_daily_mean"] = round(
                sum(daily_avgs) / len(daily_avgs), 2
            )
    return out
