"""GraphQL dnsAnalyticsAdaptiveGroups (DNS analytics)."""

from __future__ import annotations

from typing import Any

from cloudflare_executive_report.cf_client import CloudflareClient


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

# Dimensions are selected on each query (matches Cloudflare GraphQL examples).
# Note: this API does not expose sum { requests } or processingTimeUs on dnsAnalyticsAdaptiveGroups.
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


def fetch_dns_day(
    client: CloudflareClient,
    zone_id: str,
    since: str,
    until: str,
) -> dict[str, Any]:
    """
    Fetch one UTC day [since, until) of DNS analytics.
    since/until must be ISO 8601 Z as required by the API.
    """
    total_data = client.graphql(
        Q_TOTAL,
        {"zoneTag": zone_id, "since": since, "until": until},
    )
    groups = _groups(total_data)
    total_queries = sum(int(g.get("count") or 0) for g in groups)

    # No processing-time metric on this GraphQL shape for DNS adaptive groups.
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
