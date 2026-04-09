"""Security stream aggregation builder."""

from __future__ import annotations

from typing import Any

from cloudflare_executive_report.common.aggregation_helpers import (
    merge_rows,
    security_among_mitigated,
    security_challenge_and_block,
    security_coalesce_http_sampled,
    security_merge_ip_buckets,
    security_normalize_day,
    security_timeseries,
    security_top_countries,
    top_pct,
)
from cloudflare_executive_report.common.formatting import format_count_human


def build_security_section(
    daily_api_data: list[dict[str, Any]],
    *,
    top: int = 10,
) -> dict[str, Any]:
    """Roll up security daily payloads into one report section."""
    days = [security_normalize_day(day) for day in daily_api_data]
    by_action = merge_rows(days, "by_action")
    action_total = sum(by_action.values())

    mitigated = sum(int(day.get("mitigated_count") or 0) for day in days)
    served_cf = sum(int(day.get("served_cf_count") or 0) for day in days)
    served_origin = sum(int(day.get("served_origin_count") or 0) for day in days)
    http_sampled = security_coalesce_http_sampled(days, mitigated, served_cf, served_origin)
    not_mitigated = served_cf + served_origin

    among = security_among_mitigated(by_action)
    among_total = sum(among.values())
    challenge_count, block_count = security_challenge_and_block(by_action)

    by_source = merge_rows(days, "by_source")
    source_total = sum(by_source.values())
    ip_top = max(top, 20)

    cache_merged = merge_rows(days, "http_by_cache_status")
    cache_total = sum(cache_merged.values())
    method_merged = merge_rows(days, "by_http_method")
    method_total = sum(method_merged.values())
    path_merged = merge_rows(days, "by_attack_path")
    path_total = sum(path_merged.values())
    country_merged = merge_rows(days, "by_attack_country")

    mitigation_rate = 0.0
    if http_sampled > 0:
        mitigation_rate = round(100.0 * mitigated / http_sampled, 1)

    out: dict[str, Any] = {
        "total_events": action_total,
        "total_events_human": format_count_human(action_total),
        "top_actions": top_pct(by_action, action_total, top, name_key="action"),
        "timeseries_daily": security_timeseries(days),
        "top_attack_sources": security_merge_ip_buckets(days, top=ip_top),
        "top_source_countries": security_top_countries(country_merged, top=ip_top),
        "cache_status_breakdown": top_pct(cache_merged, cache_total, top, name_key="status")
        if cache_total > 0
        else [],
        "http_methods_breakdown": top_pct(method_merged, method_total, top, name_key="method")
        if method_total > 0
        else [],
        "top_attack_paths": top_pct(path_merged, path_total, top, name_key="path")
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
        out["challenge_events_sampled"] = challenge_count
        out["challenge_events_sampled_human"] = format_count_human(challenge_count)
        out["block_events_sampled"] = block_count
        out["block_events_sampled_human"] = format_count_human(block_count)
    if among_total > 0:
        out["actions_among_mitigated"] = top_pct(among, among_total, top, name_key="action")
    out["top_security_services"] = (
        top_pct(by_source, source_total, top, name_key="service") if source_total > 0 else []
    )
    return out
