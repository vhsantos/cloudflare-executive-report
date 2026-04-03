"""HTTP analytics (GraphQL httpRequests1dGroups)."""

from __future__ import annotations

from datetime import date
from typing import Any, ClassVar

from cloudflare_executive_report.cf_client import (
    CloudflareAPIError,
    CloudflareClient,
    CloudflareRateLimitError,
)
from cloudflare_executive_report.dates import format_ymd, utc_today
from cloudflare_executive_report.retention import date_outside_http_retention


def _http_groups(data: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not data:
        return []
    zones = ((data.get("viewer") or {}).get("zones")) or []
    if not zones:
        return []
    return zones[0].get("httpRequests1dGroups") or []


Q_HTTP_DAY = """
query GetHTTP($zoneTag: String!, $since: String!, $until: String!) {
  viewer {
    zones(filter: {zoneTag_in: [$zoneTag]}) {
      httpRequests1dGroups(
        limit: 1000
        filter: {date_geq: $since, date_leq: $until}
      ) {
        dimensions { date }
        sum {
          requests
          bytes
          cachedRequests
          cachedBytes
          encryptedRequests
          encryptedBytes
          pageViews
          countryMap {
            clientCountryName
            requests
            bytes
          }
        }
        uniq { uniques }
      }
    }
  }
}
"""


def fetch_http_for_date(
    client: CloudflareClient,
    zone_id: str,
    date_yyyy_mm_dd: str,
) -> dict[str, Any]:
    data = client.graphql(
        Q_HTTP_DAY,
        {"zoneTag": zone_id, "since": date_yyyy_mm_dd, "until": date_yyyy_mm_dd},
    )
    groups = _http_groups(data)
    total_req = 0
    total_bytes = 0
    total_cached_req = 0
    total_cached_bytes = 0
    total_enc_req = 0
    total_enc_bytes = 0
    total_page_views = 0
    total_uniques = 0
    country_map: dict[str, dict[str, int]] = {}

    for g in groups:
        s = g.get("sum") or {}
        total_req += int(s.get("requests") or 0)
        total_bytes += int(s.get("bytes") or 0)
        total_cached_req += int(s.get("cachedRequests") or 0)
        total_cached_bytes += int(s.get("cachedBytes") or 0)
        total_enc_req += int(s.get("encryptedRequests") or 0)
        total_enc_bytes += int(s.get("encryptedBytes") or 0)
        total_page_views += int(s.get("pageViews") or 0)
        u = (g.get("uniq") or {}).get("uniques")
        if u is not None:
            total_uniques += int(u)
        for row in s.get("countryMap") or []:
            if not isinstance(row, dict):
                continue
            name = row.get("clientCountryName")
            if name is None:
                continue
            key = str(name)
            rq = int(row.get("requests") or 0)
            bt = int(row.get("bytes") or 0)
            if key not in country_map:
                country_map[key] = {"requests": 0, "bytes": 0}
            country_map[key]["requests"] += rq
            country_map[key]["bytes"] += bt

    country_rows = [
        {"clientCountryName": k, "requests": v["requests"], "bytes": v["bytes"]}
        for k, v in sorted(country_map.items(), key=lambda x: -x[1]["requests"])
    ]

    return {
        "date": date_yyyy_mm_dd,
        "requests": total_req,
        "bytes": total_bytes,
        "cached_requests": total_cached_req,
        "cached_bytes": total_cached_bytes,
        "encrypted_requests": total_enc_req,
        "encrypted_bytes": total_enc_bytes,
        "page_views": total_page_views,
        "uniques": total_uniques,
        "country_map": country_rows,
    }


class HttpFetcher:
    stream_id: ClassVar[str] = "http"
    cache_filename: ClassVar[str] = "http.json"
    collect_label: ClassVar[str] = "HTTP"

    def outside_retention(self, day: date, *, plan_legacy_id: str | None) -> bool:
        _ = plan_legacy_id
        return date_outside_http_retention(day)

    def fetch(self, client: CloudflareClient, zone_id: str, day: date) -> dict[str, Any]:
        return fetch_http_for_date(client, zone_id, format_ymd(day))

    def append_live_today(
        self,
        client: CloudflareClient,
        zone_id: str,
        zone_name: str,
        *,
        plan_legacy_id: str | None,
    ) -> tuple[list[dict[str, Any]], list[str], bool]:
        _ = plan_legacy_id
        t = utc_today()
        if date_outside_http_retention(t):
            return [], [], False
        try:
            ht = fetch_http_for_date(client, zone_id, format_ymd(t))
            return (
                [ht],
                [
                    "Report includes today's UTC date; "
                    "HTTP data may be incomplete until the day finishes."
                ],
                False,
            )
        except CloudflareRateLimitError:
            return (
                [],
                [f"Could not fetch today's HTTP data for zone {zone_name} (rate limited)."],
                True,
            )
        except CloudflareAPIError as e:
            return ([], [f"Could not fetch today's HTTP data for zone {zone_name}: {e}"], False)
