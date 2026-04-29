"""HTTP stream rules: 5xx errors, latency, cache efficiency.

Only evaluated when the ``http`` stream is present in the report.
"""

from __future__ import annotations

from cloudflare_executive_report.common.constants import (
    BANDWIDTH_GB_MIN_THRESHOLD,
    CACHE_DELTA_WARNING_PP,
    CACHE_HIT_RATIO_LOW_THRESHOLD,
    LATENCY_DELTA_WARNING_MS,
    LATENCY_DELTA_WIN_MS,
    LATENCY_WARNING_MS,
    RELIABILITY_5XX_HEALTHY_MAX,
    RELIABILITY_5XX_WARNING_MAX,
    TRAFFIC_DELTA_PCT_THRESHOLD,
)
from cloudflare_executive_report.common.safe_types import as_dict, as_float, as_int
from cloudflare_executive_report.executive.rules import (
    SECT_DELTAS,
    SECT_SIGNALS,
    SECT_WINS,
)
from cloudflare_executive_report.executive.rules._context import (
    RuleContext,
    add_takeaway,
    percent_delta,
    pp_delta,
)


def evaluate(ctx: RuleContext) -> None:
    """Evaluate HTTP/cache stream rules. No-op when http stream is absent."""
    if not ctx.available_streams.get("http", False):
        return

    http = as_dict(ctx.current_zone.get("http"))
    cache = as_dict(ctx.current_zone.get("cache"))
    ha = as_dict(ctx.current_zone.get("http_adaptive"))

    err_5xx = as_float(ha.get("status_5xx_rate_pct"))
    latency = as_float(ha.get("origin_response_duration_avg_ms"))
    cache_hit = as_float(cache.get("cache_hit_ratio") or http.get("cache_hit_ratio"))
    bandwidth_gb = as_int(http.get("total_bandwidth_bytes")) / (1024.0**3)

    if err_5xx > RELIABILITY_5XX_WARNING_MAX:
        e5 = round(err_5xx, 2)
        add_takeaway(
            ctx, SECT_SIGNALS, "critical", "origin_errors_high", state="observation", err_pct=e5
        )
    elif err_5xx > RELIABILITY_5XX_HEALTHY_MAX and latency > LATENCY_WARNING_MS:
        e5, lms = round(err_5xx, 2), round(latency)
        add_takeaway(
            ctx,
            SECT_SIGNALS,
            "warning",
            "origin_health",
            state="observation",
            err_pct=e5,
            latency_ms=lms,
        )

    if cache_hit < CACHE_HIT_RATIO_LOW_THRESHOLD and bandwidth_gb > BANDWIDTH_GB_MIN_THRESHOLD:
        ch, gbw = round(cache_hit, 1), round(bandwidth_gb)
        add_takeaway(
            ctx,
            SECT_SIGNALS,
            "warning",
            "cache_efficiency",
            state="observation",
            cache_hit=ch,
            bandwidth_gb=gbw,
        )

    # ------------------------------------------------------------------
    # HTTP / traffic deltas
    # ------------------------------------------------------------------
    if ctx.previous_zone and ctx.comparison_allowed:
        p_http = as_dict(ctx.previous_zone.get("http"))
        p_ha = as_dict(ctx.previous_zone.get("http_adaptive"))

        pct_traffic = percent_delta(
            as_int(http.get("total_requests")),
            as_int(p_http.get("total_requests")),
        )
        if abs(pct_traffic) > TRAFFIC_DELTA_PCT_THRESHOLD:
            if pct_traffic > 0:
                pct_i = round(pct_traffic)
                add_takeaway(ctx, SECT_DELTAS, "info", "traffic_up", state="comparison", pct=pct_i)
                add_takeaway(ctx, SECT_WINS, "positive", "traffic_up", state="win", pct=pct_i)
            else:
                pct_dn = abs(round(pct_traffic))
                add_takeaway(
                    ctx, SECT_DELTAS, "warning", "traffic_down", state="comparison", pct=pct_dn
                )

        cache_delta = pp_delta(
            as_float(cache.get("cache_hit_ratio") or http.get("cache_hit_ratio")),
            as_float(p_http.get("cache_hit_ratio")),
        )
        if cache_delta < CACHE_DELTA_WARNING_PP:
            pp_dn = abs(round(cache_delta))
            add_takeaway(
                ctx, SECT_DELTAS, "warning", "cache_efficiency", state="comparison", pp=pp_dn
            )

        # ------------------------------------------------------------------
        # Latency deltas (http_adaptive)
        # ------------------------------------------------------------------
        latency_delta = as_float(ha.get("origin_response_duration_avg_ms")) - as_float(
            p_ha.get("origin_response_duration_avg_ms")
        )
        if latency_delta > LATENCY_DELTA_WARNING_MS:
            ms_up = round(latency_delta)
            add_takeaway(ctx, SECT_DELTAS, "warning", "latency_delta", state="comparison", ms=ms_up)
        elif latency_delta < LATENCY_DELTA_WIN_MS:
            ms_dn = abs(round(latency_delta))
            add_takeaway(ctx, SECT_WINS, "positive", "latency_delta", state="win", ms=ms_dn)
