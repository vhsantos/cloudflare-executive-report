"""DNS analytics (GraphQL dnsAnalyticsAdaptiveGroups)."""

from __future__ import annotations

from datetime import date
from typing import Any, ClassVar

from cloudflare_executive_report.cf_client import (
    CloudflareAPIError,
    CloudflareClient,
    CloudflareRateLimitError,
)
from cloudflare_executive_report.common.dates import day_bounds_utc, utc_today
from cloudflare_executive_report.common.retention import (
    date_outside_dns_retention,
    dns_retention_days,
)

Q_TOTAL = """
query DnsTotal($zoneTag: String!, $since: String!, $until: String!) {
  viewer {
    zones(filter: {zoneTag_in: [$zoneTag]}) {
      dnsAnalyticsAdaptiveGroups(
        limit: 1000
        filter: {datetime_geq: $since, datetime_lt: $until}
      ) {
        count
      }
    }
  }
}
"""


Q_BATCH_DIM = """
query DnsBatch($zoneTag: String!, $since: String!, $until: String!, $limit: Int!) {
  viewer {
    zones(filter: {zoneTag_in: [$zoneTag]}) {
      by_query_name: dnsAnalyticsAdaptiveGroups(
        limit: $limit
        filter: {datetime_geq: $since, datetime_lt: $until}
        orderBy: [count_DESC]
      ) {
        count
        dimensions { queryName }
      }
      by_query_type: dnsAnalyticsAdaptiveGroups(
        limit: $limit
        filter: {datetime_geq: $since, datetime_lt: $until}
        orderBy: [count_DESC]
      ) {
        count
        dimensions { queryType }
      }
      by_response: dnsAnalyticsAdaptiveGroups(
        limit: $limit
        filter: {datetime_geq: $since, datetime_lt: $until}
        orderBy: [count_DESC]
      ) {
        count
        dimensions { responseCode }
      }
      by_colo: dnsAnalyticsAdaptiveGroups(
        limit: $limit
        filter: {datetime_geq: $since, datetime_lt: $until}
        orderBy: [count_DESC]
      ) {
        count
        dimensions { coloName }
      }
      by_protocol: dnsAnalyticsAdaptiveGroups(
        limit: $limit
        filter: {datetime_geq: $since, datetime_lt: $until}
        orderBy: [count_DESC]
      ) {
        count
        dimensions { protocol }
      }
      by_ip_version: dnsAnalyticsAdaptiveGroups(
        limit: $limit
        filter: {datetime_geq: $since, datetime_lt: $until}
        orderBy: [count_DESC]
      ) {
        count
        dimensions { ipVersion }
      }
    }
  }
}
"""


def _groups_base(data: dict[str, Any] | None) -> dict[str, Any]:
    if not data:
        return {}
    zones = ((data.get("viewer") or {}).get("zones")) or []
    if not zones:
        return {}
    return zones[0]


def _groups(data: dict[str, Any] | None) -> list[dict[str, Any]]:
    return _groups_base(data).get("dnsAnalyticsAdaptiveGroups") or []


def _rows_to_value_count(rows: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        dims = row.get("dimensions") or {}
        key = dims.get(field)
        if key is None:
            continue
        out.append({"value": str(key), "count": int(row.get("count") or 0)})
    return out


def fetch_dns_for_bounds(
    client: CloudflareClient,
    zone_id: str,
    since: str,
    until: str,
) -> dict[str, Any]:
    """One UTC window [since, until) of DNS analytics (ISO 8601 Z)."""
    total_data = client.graphql(
        Q_TOTAL,
        {"zoneTag": zone_id, "since": since, "until": until},
    )
    groups = _groups(total_data)
    total_queries = sum(int(g.get("count") or 0) for g in groups)
    avg_pt_us: float | None = None

    batch_data = client.graphql(
        Q_BATCH_DIM,
        {
            "zoneTag": zone_id,
            "since": since,
            "until": until,
            "limit": 500,
        },
    )
    base = _groups_base(batch_data)

    by_query_name = _rows_to_value_count(base.get("by_query_name") or [], "queryName")
    by_query_type = _rows_to_value_count(base.get("by_query_type") or [], "queryType")
    by_response = _rows_to_value_count(base.get("by_response") or [], "responseCode")
    by_colo = _rows_to_value_count(base.get("by_colo") or [], "coloName")
    by_protocol = _rows_to_value_count(base.get("by_protocol") or [], "protocol")
    by_ip_version = _rows_to_value_count(base.get("by_ip_version") or [], "ipVersion")

    return {
        "total_queries": total_queries,
        "avg_processing_time_us": avg_pt_us,
        "by_query_name": by_query_name,
        "by_query_type": by_query_type,
        "by_response_code": by_response,
        "by_colo": by_colo,
        "by_protocol": by_protocol,
        "by_ip_version": by_ip_version,
    }


class DnsFetcher:
    stream_id: ClassVar[str] = "dns"
    cache_filename: ClassVar[str] = "dns.json"
    collect_label: ClassVar[str] = "DNS"
    required_permissions: ClassVar[tuple[str, ...]] = (
        "Zone > Zone Read",
        "Zone > Analytics Read",
    )

    def outside_retention(self, day: date, *, plan_legacy_id: str | None) -> bool:
        return date_outside_dns_retention(day, dns_retention_days(plan_legacy_id))

    def fetch(
        self,
        client: CloudflareClient,
        zone_id: str,
        day: date,
        *,
        zone_meta: dict[str, Any] | None,
    ) -> dict[str, Any]:
        _ = zone_meta
        ge, lt = day_bounds_utc(day)
        return fetch_dns_for_bounds(client, zone_id, ge, lt)

    def append_live_today(
        self,
        client: CloudflareClient,
        zone_id: str,
        zone_name: str,
        *,
        plan_legacy_id: str | None,
        zone_meta: dict[str, Any] | None,
    ) -> tuple[list[dict[str, Any]], list[str], bool]:
        _ = zone_meta
        t = utc_today()
        if date_outside_dns_retention(t, dns_retention_days(plan_legacy_id)):
            return [], [], False
        ge, lt = day_bounds_utc(t)
        try:
            d = fetch_dns_for_bounds(client, zone_id, ge, lt)
            return (
                [d],
                [
                    "Report includes today's UTC date; "
                    "DNS data may be incomplete until the day finishes."
                ],
                False,
            )
        except CloudflareRateLimitError:
            return (
                [],
                [f"Could not fetch today's DNS data for zone {zone_name} (rate limited)."],
                True,
            )
        except CloudflareAPIError as e:
            return ([], [f"Could not fetch today's DNS data for zone {zone_name}: {e}"], False)
