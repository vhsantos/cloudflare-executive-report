"""HTTP adaptive analytics (status mix + optional latency quantiles)."""

from __future__ import annotations

from datetime import date
from typing import Any, ClassVar

from cloudflare_executive_report.cf_client import (
    CloudflareAPIError,
    CloudflareClient,
    CloudflareRateLimitError,
)
from cloudflare_executive_report.common.dates import (
    day_bounds_utc,
    format_ymd,
    utc_now_z,
    utc_today,
)
from cloudflare_executive_report.common.retention import date_outside_http_retention
from cloudflare_executive_report.fetchers.graphql_common import adaptive_groups_rows

Q_HTTP_ADAPTIVE_STATUS = """
query HttpAdaptiveStatus($zoneTag: String!, $datetime_geq: Time!, $datetime_lt: Time!) {
  viewer {
    zones(filter: {zoneTag_in: [$zoneTag]}) {
      st: httpRequestsAdaptiveGroups(
        limit: 10000
        orderBy: [count_DESC]
        filter: {
          datetime_geq: $datetime_geq
          datetime_lt: $datetime_lt
          requestSource: "eyeball"
        }
      ) {
        count
        dimensions { edgeResponseStatus }
      }
    }
  }
}
"""

# Timing Insights fields are plan/feature dependent; keep queries optional/fallback.
Q_HTTP_ADAPTIVE_TIMING_AVG = """
query HttpAdaptiveTimingAvg($zoneTag: String!, $datetime_geq: Time!, $datetime_lt: Time!) {
  viewer {
    zones(filter: {zoneTag_in: [$zoneTag]}) {
      tm: httpRequestsAdaptiveGroups(
        limit: 1
        filter: {
          datetime_geq: $datetime_geq
          datetime_lt: $datetime_lt
          requestSource: "eyeball"
        }
      ) {
        avg {
          edgeTimeToFirstByteMsP50
          edgeTimeToFirstByteMsP95
        }
      }
    }
  }
}
"""

Q_HTTP_ADAPTIVE_TIMING_QUANTILES = """
query HttpAdaptiveTimingQuantiles($zoneTag: String!, $datetime_geq: Time!, $datetime_lt: Time!) {
  viewer {
    zones(filter: {zoneTag_in: [$zoneTag]}) {
      tm: httpRequestsAdaptiveGroups(
        limit: 1
        filter: {
          datetime_geq: $datetime_geq
          datetime_lt: $datetime_lt
          requestSource: "eyeball"
        }
      ) {
        quantiles {
          edgeTimeToFirstByteMsP50
          edgeTimeToFirstByteMsP95
        }
      }
    }
  }
}
"""

Q_HTTP_ADAPTIVE_TIMING_ORIGIN_AVG = """
query HttpAdaptiveOriginTimingAvg($zoneTag: String!, $datetime_geq: Time!, $datetime_lt: Time!) {
  viewer {
    zones(filter: {zoneTag_in: [$zoneTag]}) {
      tm: httpRequestsAdaptiveGroups(
        limit: 1
        filter: {
          datetime_geq: $datetime_geq
          datetime_lt: $datetime_lt
          requestSource: "eyeball"
        }
      ) {
        avg {
          originResponseDurationMs
        }
      }
    }
  }
}
"""


def _error_status_bucket(status: str) -> str:
    s = status.strip()
    if not s:
        return ""
    try:
        v = int(s)
    except ValueError:
        return ""
    if 400 <= v <= 499:
        return "4xx"
    if 500 <= v <= 599:
        return "5xx"
    return ""


def _status_rows_rollup(
    rows: list[dict[str, Any]],
) -> tuple[int, int, int, list[dict[str, int | str]]]:
    total = 0
    n4 = 0
    n5 = 0
    merged: dict[str, int] = {}
    for row in rows:
        dims = row.get("dimensions") or {}
        if not isinstance(dims, dict):
            continue
        code = str(dims.get("edgeResponseStatus") or "").strip()
        if not code:
            continue
        c = int(row.get("count") or 0)
        total += c
        merged[code] = merged.get(code, 0) + c
        bucket = _error_status_bucket(code)
        if bucket == "4xx":
            n4 += c
        elif bucket == "5xx":
            n5 += c
    status_rows = [{"value": k, "count": v} for k, v in sorted(merged.items(), key=lambda x: -x[1])]
    return total, n4, n5, status_rows


def _timing_p50_p95_from_data_avg(data: dict[str, Any] | None) -> tuple[float | None, float | None]:
    rows = adaptive_groups_rows(data, "tm")
    if not rows:
        return None, None
    avg = rows[0].get("avg") or {}
    if not isinstance(avg, dict):
        return None, None
    p50 = avg.get("edgeTimeToFirstByteMsP50")
    p95 = avg.get("edgeTimeToFirstByteMsP95")
    return (float(p50) if p50 is not None else None, float(p95) if p95 is not None else None)


def _timing_p50_p95_from_data_quantiles(
    data: dict[str, Any] | None,
) -> tuple[float | None, float | None]:
    rows = adaptive_groups_rows(data, "tm")
    if not rows:
        return None, None
    q = rows[0].get("quantiles") or {}
    if not isinstance(q, dict):
        return None, None
    p50 = q.get("edgeTimeToFirstByteMsP50")
    p95 = q.get("edgeTimeToFirstByteMsP95")
    return (float(p50) if p50 is not None else None, float(p95) if p95 is not None else None)


def _fetch_optional_timing_ms(
    client: CloudflareClient, vars_gql: dict[str, str]
) -> tuple[float | None, float | None]:
    def is_terminal_timing_error(msg: str) -> bool:
        m = msg.lower()
        return (
            "unknown field" in m or "cannot query field" in m or "rate limiter budget depleted" in m
        )

    try:
        data = client.graphql(Q_HTTP_ADAPTIVE_TIMING_AVG, vars_gql)
        p50, p95 = _timing_p50_p95_from_data_avg(data)
        if p50 is not None or p95 is not None:
            return p50, p95
    except CloudflareAPIError as e:
        if is_terminal_timing_error(str(e)):
            return None, None
    try:
        data = client.graphql(Q_HTTP_ADAPTIVE_TIMING_QUANTILES, vars_gql)
        p50, p95 = _timing_p50_p95_from_data_quantiles(data)
        if p50 is not None or p95 is not None:
            return p50, p95
    except CloudflareAPIError as e:
        if is_terminal_timing_error(str(e)):
            return None, None
    return None, None


def _fetch_optional_origin_response_ms(
    client: CloudflareClient, vars_gql: dict[str, str]
) -> float | None:
    try:
        data = client.graphql(Q_HTTP_ADAPTIVE_TIMING_ORIGIN_AVG, vars_gql)
        rows = adaptive_groups_rows(data, "tm")
        if not rows:
            return None
        avg = rows[0].get("avg") or {}
        if not isinstance(avg, dict):
            return None
        v = avg.get("originResponseDurationMs")
        return float(v) if v is not None else None
    except CloudflareAPIError:
        return None


def fetch_http_adaptive_for_bounds(
    client: CloudflareClient,
    zone_id: str,
    since_iso_z: str,
    until_iso_z: str,
) -> dict[str, Any]:
    vars_gql = {"zoneTag": zone_id, "datetime_geq": since_iso_z, "datetime_lt": until_iso_z}
    rows = adaptive_groups_rows(client.graphql(Q_HTTP_ADAPTIVE_STATUS, vars_gql), "st")
    total, n4, n5, by_status = _status_rows_rollup(rows)
    p50, p95 = _fetch_optional_timing_ms(client, vars_gql)
    origin_avg = _fetch_optional_origin_response_ms(client, vars_gql)
    out: dict[str, Any] = {
        "http_requests_analyzed": total,
        "status_4xx_count": n4,
        "status_5xx_count": n5,
        "status_4xx_rate_pct": round(100.0 * n4 / total, 2) if total > 0 else 0.0,
        "status_5xx_rate_pct": round(100.0 * n5 / total, 2) if total > 0 else 0.0,
        "by_edge_status": by_status,
    }
    if p50 is not None:
        out["latency_p50_ms"] = round(p50, 2)
    if p95 is not None:
        out["latency_p95_ms"] = round(p95, 2)
    if origin_avg is not None:
        out["origin_response_duration_avg_ms"] = round(origin_avg, 2)
    return out


def fetch_http_adaptive_for_date(
    client: CloudflareClient,
    zone_id: str,
    day: date,
) -> dict[str, Any]:
    geq, lt = day_bounds_utc(day)
    payload = fetch_http_adaptive_for_bounds(client, zone_id, geq, lt)
    payload["date"] = format_ymd(day)
    return payload


class HttpAdaptiveFetcher:
    stream_id: ClassVar[str] = "http_adaptive"
    cache_filename: ClassVar[str] = "http_adaptive.json"
    collect_label: ClassVar[str] = "HTTP adaptive"
    required_permissions: ClassVar[tuple[str, ...]] = (
        "Zone > Zone Read",
        "Zone > Analytics Read",
    )

    def outside_retention(self, day: date, *, plan_legacy_id: str | None) -> bool:
        _ = plan_legacy_id
        return date_outside_http_retention(day)

    def fetch(
        self,
        client: CloudflareClient,
        zone_id: str,
        day: date,
        *,
        zone_meta: dict[str, Any] | None,
    ) -> dict[str, Any]:
        _ = zone_meta
        return fetch_http_adaptive_for_date(client, zone_id, day)

    def append_live_today(
        self,
        client: CloudflareClient,
        zone_id: str,
        zone_name: str,
        *,
        plan_legacy_id: str | None,
        zone_meta: dict[str, Any] | None,
    ) -> tuple[list[dict[str, Any]], list[str], bool]:
        _ = (plan_legacy_id, zone_meta)
        t = utc_today()
        if date_outside_http_retention(t):
            return [], [], False
        try:
            payload = fetch_http_adaptive_for_bounds(
                client, zone_id, day_bounds_utc(t)[0], utc_now_z()
            )
            payload["date"] = format_ymd(t)
            return (
                [payload],
                [
                    "Report includes today's UTC date; "
                    "adaptive HTTP analytics may be incomplete until the day finishes."
                ],
                False,
            )
        except CloudflareRateLimitError:
            return (
                [],
                [
                    f"Could not fetch today's adaptive HTTP data for zone {zone_name} "
                    "(rate limited)."
                ],
                True,
            )
        except CloudflareAPIError as e:
            return (
                [],
                [f"Could not fetch today's adaptive HTTP data for zone {zone_name}: {e}"],
                False,
            )
