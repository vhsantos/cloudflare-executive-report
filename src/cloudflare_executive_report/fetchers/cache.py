"""Per-day cache analytics via ``httpRequestsAdaptiveGroups`` (eyeball traffic)."""

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
    day_start_iso_z,
    format_ymd,
    utc_now_z,
    utc_today,
)
from cloudflare_executive_report.common.retention import date_outside_http_retention
from cloudflare_executive_report.fetchers.graphql_common import (
    adaptive_groups_rows,
    marginal_counts_and_sums_for_dimension,
    row_sum_int,
)

_LIMIT_CACHE_STATUS = 100
_LIMIT_PATH_STATUS = 100

Q_CACHE_DAY = f"""
query CacheDay($zoneTag: String!, $datetime_geq: Time!, $datetime_lt: Time!) {{
  viewer {{
    zones(filter: {{zoneTag_in: [$zoneTag]}}) {{
      cst: httpRequestsAdaptiveGroups(
        limit: {_LIMIT_CACHE_STATUS}
        filter: {{
          datetime_geq: $datetime_geq
          datetime_lt: $datetime_lt
          requestSource: "eyeball"
        }}
        orderBy: [count_DESC]
      ) {{
        count
        dimensions {{ cacheStatus }}
        sum {{ edgeResponseBytes }}
      }}
      pth: httpRequestsAdaptiveGroups(
        limit: {_LIMIT_PATH_STATUS}
        filter: {{
          datetime_geq: $datetime_geq
          datetime_lt: $datetime_lt
          requestSource: "eyeball"
        }}
        orderBy: [count_DESC]
      ) {{
        count
        dimensions {{ clientRequestPath cacheStatus }}
        sum {{ edgeResponseBytes }}
      }}
    }}
  }}
}}
"""


def _pair_rows(
    rows: list[dict[str, Any]],
    *,
    key_a: str,
    key_b: str,
    out_a: str,
    out_b: str,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        dims = row.get("dimensions") or {}
        if not isinstance(dims, dict):
            continue
        va = str(dims.get(key_a) or "").strip()
        vb = str(dims.get(key_b) or "").strip()
        if not va or not vb:
            continue
        out.append(
            {
                out_a: va,
                out_b: vb,
                "count": int(row.get("count") or 0),
                "edgeResponseBytes": row_sum_int(row, "edgeResponseBytes"),
            }
        )
    return out


def fetch_cache_for_bounds(
    client: CloudflareClient,
    zone_id: str,
    since_iso_z: str,
    until_iso_z: str,
) -> dict[str, Any]:
    vars_gql = {"zoneTag": zone_id, "datetime_geq": since_iso_z, "datetime_lt": until_iso_z}
    data = client.graphql(Q_CACHE_DAY, vars_gql)
    status_rows = adaptive_groups_rows(data, "cst")
    path_rows = adaptive_groups_rows(data, "pth")

    by_status = marginal_counts_and_sums_for_dimension(
        status_rows,
        "cacheStatus",
        sum_field="edgeResponseBytes",
        out_sum_key="edgeResponseBytes",
    )
    return {
        "by_cache_status": by_status,
        "top_path_status": _pair_rows(
            path_rows,
            key_a="clientRequestPath",
            key_b="cacheStatus",
            out_a="path",
            out_b="cacheStatus",
        ),
        "payload_kind": "http_cache_groups",
    }


def fetch_cache_for_date(
    client: CloudflareClient,
    zone_id: str,
    day: date,
) -> dict[str, Any]:
    geq, lt = day_bounds_utc(day)
    payload = fetch_cache_for_bounds(client, zone_id, geq, lt)
    payload["date"] = format_ymd(day)
    return payload


class CacheFetcher:
    stream_id: ClassVar[str] = "cache"
    cache_filename: ClassVar[str] = "cache.json"
    collect_label: ClassVar[str] = "Cache"

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
        return fetch_cache_for_date(client, zone_id, day)

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
            payload = fetch_cache_for_bounds(
                client,
                zone_id,
                day_start_iso_z(t),
                utc_now_z(),
            )
            payload["date"] = format_ymd(t)
            return (
                [payload],
                [
                    "Report includes today's UTC date; "
                    "cache analytics may be incomplete until the day finishes."
                ],
                False,
            )
        except CloudflareRateLimitError:
            return (
                [],
                [f"Could not fetch today's cache data for zone {zone_name} (rate limited)."],
                True,
            )
        except CloudflareAPIError as e:
            return ([], [f"Could not fetch today's cache data for zone {zone_name}: {e}"], False)
