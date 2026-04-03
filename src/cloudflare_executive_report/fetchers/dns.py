"""DNS analytics (GraphQL dnsAnalyticsAdaptiveGroups)."""

from __future__ import annotations

from datetime import date
from typing import Any, ClassVar

from cloudflare_executive_report.cf_client import (
    CloudflareAPIError,
    CloudflareClient,
    CloudflareRateLimitError,
)
from cloudflare_executive_report.dates import day_bounds_utc, utc_today
from cloudflare_executive_report.retention import date_outside_dns_retention, dns_retention_days


def _groups(data: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not data:
        return []
    zones = ((data.get("viewer") or {}).get("zones")) or []
    if not zones:
        return []
    return zones[0].get("dnsAnalyticsAdaptiveGroups") or []


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

Q_DIM = """
query DnsDim%(suffix)s($zoneTag: String!, $since: String!, $until: String!, $limit: Int!) {
  viewer {
    zones(filter: {zoneTag_in: [$zoneTag]}) {
      dnsAnalyticsAdaptiveGroups(
        limit: $limit
        filter: {datetime_geq: $since, datetime_lt: $until}
        orderBy: [count_DESC]
      ) {
        count
        dimensions {
          %(field)s
        }
      }
    }
  }
}
"""


def _dim_queries() -> dict[str, str]:
    fields = [
        ("queryName", "QueryName"),
        ("queryType", "QueryType"),
        ("responseCode", "ResponseCode"),
        ("coloName", "ColoName"),
        ("sourceIP", "SourceIP"),
        ("destinationIP", "DestinationIP"),
        ("protocol", "Protocol"),
        ("ipVersion", "IpVersion"),
    ]
    return {f: Q_DIM % {"suffix": suf, "field": f} for f, suf in fields}


_DIM_QUERIES = _dim_queries()


def _fetch_dim(
    client: CloudflareClient,
    zone_id: str,
    since: str,
    until: str,
    field: str,
    limit: int = 500,
) -> list[dict[str, Any]]:
    q = _DIM_QUERIES[field]
    data = client.graphql(
        q,
        {
            "zoneTag": zone_id,
            "since": since,
            "until": until,
            "limit": limit,
        },
    )
    rows = _groups(data)
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

    by_query_name = _fetch_dim(client, zone_id, since, until, "queryName")
    by_query_type = _fetch_dim(client, zone_id, since, until, "queryType")
    by_response = _fetch_dim(client, zone_id, since, until, "responseCode")
    by_colo = _fetch_dim(client, zone_id, since, until, "coloName")
    by_protocol = _fetch_dim(client, zone_id, since, until, "protocol")
    by_ip_version = _fetch_dim(client, zone_id, since, until, "ipVersion")

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

    def outside_retention(self, day: date, *, plan_legacy_id: str | None) -> bool:
        return date_outside_dns_retention(day, dns_retention_days(plan_legacy_id))

    def fetch(self, client: CloudflareClient, zone_id: str, day: date) -> dict[str, Any]:
        ge, lt = day_bounds_utc(day)
        return fetch_dns_for_bounds(client, zone_id, ge, lt)

    def append_live_today(
        self,
        client: CloudflareClient,
        zone_id: str,
        zone_name: str,
        *,
        plan_legacy_id: str | None,
    ) -> tuple[list[dict[str, Any]], list[str], bool]:
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
