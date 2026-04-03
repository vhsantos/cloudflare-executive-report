"""Firewall / security events (GraphQL firewallEventsAdaptive).

Note: ``firewallEventsAdaptiveGroups`` is a different GraphQL path and often returns
"zone does not have access to the path" for the same token that can read
``firewallEventsAdaptive`` (raw sampled events). We use the adaptive node and fold
rows into ``by_action`` counts for a compact cache.
"""

from __future__ import annotations

from datetime import date
from typing import Any, ClassVar

from cloudflare_executive_report.cf_client import (
    CloudflareAPIError,
    CloudflareClient,
    CloudflareRateLimitError,
)
from cloudflare_executive_report.dates import day_start_iso_z, format_ymd, utc_now_iso_z, utc_today
from cloudflare_executive_report.retention import date_outside_security_retention

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


def _end_of_utc_calendar_day_iso_z(d: date) -> str:
    """Inclusive upper bound for ``datetime_leq`` on a stored UTC calendar day."""
    return f"{format_ymd(d)}T23:59:59Z"


def _security_rows(data: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not data:
        return []
    zones = ((data.get("viewer") or {}).get("zones")) or []
    if not zones:
        return []
    return zones[0].get("firewallEventsAdaptive") or []


def _rows_to_by_action(rows: list[dict[str, Any]]) -> dict[str, Any]:
    merged: dict[str, int] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        act = row.get("action")
        if act is None:
            continue
        key = str(act)
        merged[key] = merged.get(key, 0) + 1
    by_action = [{"value": k, "count": c} for k, c in merged.items()]
    total = sum(merged.values())
    return {"by_action": by_action, "total_events": total}


def fetch_security_for_bounds(
    client: CloudflareClient,
    zone_id: str,
    since_iso_z: str,
    until_iso_z: str,
) -> dict[str, Any]:
    """
    Sampled firewall events in [since_iso_z, until_iso_z] per ``datetime_leq`` (inclusive end).
    Response is folded into ``by_action`` counts (cap: 10000 rows per request).
    """
    data = client.graphql(
        Q_SECURITY,
        {"zoneTag": zone_id, "since": since_iso_z, "until": until_iso_z},
    )
    rows = _security_rows(data)
    return _rows_to_by_action(rows)


def fetch_security_for_date(
    client: CloudflareClient,
    zone_id: str,
    day: date,
) -> dict[str, Any]:
    return fetch_security_for_bounds(
        client,
        zone_id,
        day_start_iso_z(day),
        _end_of_utc_calendar_day_iso_z(day),
    )


class SecurityFetcher:
    stream_id: ClassVar[str] = "security"
    cache_filename: ClassVar[str] = "security.json"
    collect_label: ClassVar[str] = "Security"

    def outside_retention(self, day: date, *, plan_legacy_id: str | None) -> bool:
        _ = plan_legacy_id
        return date_outside_security_retention(day)

    def fetch(self, client: CloudflareClient, zone_id: str, day: date) -> dict[str, Any]:
        return fetch_security_for_date(client, zone_id, day)

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
        if date_outside_security_retention(t):
            return [], [], False
        try:
            payload = fetch_security_for_bounds(
                client,
                zone_id,
                day_start_iso_z(t),
                utc_now_iso_z(),
            )
            return (
                [payload],
                [
                    "Report includes today's UTC date; "
                    "security event data may be incomplete until the day finishes."
                ],
                False,
            )
        except CloudflareRateLimitError:
            return (
                [],
                [f"Could not fetch today's security data for zone {zone_name} (rate limited)."],
                True,
            )
        except CloudflareAPIError as e:
            return ([], [f"Could not fetch today's security data for zone {zone_name}: {e}"], False)
