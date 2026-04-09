"""DNS stream aggregation builder."""

from __future__ import annotations

from typing import Any

from cloudflare_executive_report.common.aggregation_helpers import merge_rows, top_pct


def build_dns_section(
    daily_api_data: list[dict[str, Any]],
    *,
    top: int = 10,
) -> dict[str, Any]:
    """Aggregate DNS daily payloads into one report section."""
    total_queries = sum(int(day.get("total_queries") or 0) for day in daily_api_data)
    seconds = 86400 * max(len(daily_api_data), 1)
    average_qps = round(total_queries / seconds, 3) if seconds else 0.0

    weighted_num = 0.0
    weighted_den = 0
    for day in daily_api_data:
        query_count = int(day.get("total_queries") or 0)
        average_processing_time = day.get("avg_processing_time_us")
        if query_count > 0 and average_processing_time is not None:
            weighted_num += float(average_processing_time) * query_count
            weighted_den += query_count
    average_processing_ms = None
    if weighted_den > 0:
        average_processing_ms = round(weighted_num / weighted_den / 1000.0, 3)

    by_query_name = merge_rows(daily_api_data, "by_query_name")
    by_query_type = merge_rows(daily_api_data, "by_query_type")
    by_response_code = merge_rows(daily_api_data, "by_response_code")
    by_colo = merge_rows(daily_api_data, "by_colo")
    by_protocol = merge_rows(daily_api_data, "by_protocol")
    by_ip_version = merge_rows(daily_api_data, "by_ip_version")

    def norm_version(value: str) -> str:
        if value in ("4", "ipv4", "IPv4"):
            return "IPv4"
        if value in ("6", "ipv6", "IPv6"):
            return "IPv6"
        return value

    ip_versions: dict[str, int] = {}
    for key, count in by_ip_version.items():
        normalized = norm_version(key)
        ip_versions[normalized] = ip_versions.get(normalized, 0) + count

    dns_section: dict[str, Any] = {
        "total_queries": total_queries,
        "average_qps": average_qps,
        "top_query_names": top_pct(by_query_name, total_queries, top, name_key="name"),
        "top_record_types": top_pct(by_query_type, total_queries, top, name_key="type"),
        "response_codes": top_pct(by_response_code, total_queries, top, name_key="code"),
        "top_data_centers": top_pct(by_colo, total_queries, top, name_key="colo"),
        "protocols": top_pct(by_protocol, total_queries, top, name_key="protocol"),
        "ip_versions": top_pct(ip_versions, total_queries, top, name_key="version"),
    }
    if average_processing_ms is not None:
        dns_section["average_processing_time_ms"] = average_processing_ms
    return dns_section
