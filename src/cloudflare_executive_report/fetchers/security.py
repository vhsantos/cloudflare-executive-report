"""Security events (GraphQL firewallEventsAdaptive)."""

from __future__ import annotations

from datetime import date
from typing import Any, ClassVar

from cloudflare_executive_report.cache.paths import CacheStream
from cloudflare_executive_report.cf_client import CloudflareClient
from cloudflare_executive_report.dates import (
    day_start_iso_z,
    security_day_bounds_inclusive_utc,
    utc_now_iso_z,
)
from cloudflare_executive_report.retention import (
    date_outside_security_retention,
    security_retention_days,
)

Q_SECURITY = """
query GetSecurity($zoneTag: String!, $since: String!, $until: String!) {
  viewer {
    zones(filter: {zoneTag_in: [$zoneTag]}) {
      firewallEventsAdaptive(
        limit: 10000
        filter: {datetime_geq: $since, datetime_leq: $until}
      ) {
        action
      }
    }
  }
}
"""


def _security_rows(data: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not data:
        return []
    zones = ((data.get("viewer") or {}).get("zones")) or []
    if not zones:
        return []
    return zones[0].get("firewallEventsAdaptive") or []


def fetch_security_for_bounds(
    client: CloudflareClient,
    zone_id: str,
    since_iso_z: str,
    until_iso_z: str,
) -> dict[str, Any]:
    data = client.graphql(
        Q_SECURITY,
        {"zoneTag": zone_id, "since": since_iso_z, "until": until_iso_z},
    )
    rows = _security_rows(data)
    events = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        act = row.get("action")
        if act is None:
            continue
        events.append({"action": str(act)})
    return {"events": events}


def fetch_security_partial_utc_day(
    client: CloudflareClient,
    zone_id: str,
    day: date,
) -> dict[str, Any]:
    """From UTC midnight through current time (for live today)."""
    return fetch_security_for_bounds(client, zone_id, day_start_iso_z(day), utc_now_iso_z())


class SecurityFetcher:
    stream: ClassVar[CacheStream] = CacheStream.security
    collect_label: ClassVar[str] = "Security"

    def outside_retention(self, day: date, *, plan_legacy_id: str | None) -> bool:
        return date_outside_security_retention(day, security_retention_days(plan_legacy_id))

    def fetch(self, client: CloudflareClient, zone_id: str, day: date) -> dict[str, Any]:
        ge, lt = security_day_bounds_inclusive_utc(day)
        return fetch_security_for_bounds(client, zone_id, ge, lt)
