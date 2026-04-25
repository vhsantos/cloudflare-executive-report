"""Skeleton fetcher - copy this file when adding a new data stream.

Replace every occurrence of ``example`` / ``Example`` / ``EXAMPLE`` with
your stream name, then fill in the GraphQL query and field mappings.

DO NOT ship this file as-is; it is a reference template only.
Delete it once you have created your real stream.
"""

from __future__ import annotations

import logging
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

# Import the appropriate retention helper for your stream.
# Use date_outside_http_retention for HTTP-based streams (90-day window),
# or date_outside_security_retention for security streams (plan-aware).
# If the stream has unlimited retention, always return False.
from cloudflare_executive_report.common.retention import date_outside_http_retention

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# GraphQL limits - name every constant; never use magic numbers.
# ---------------------------------------------------------------------------
_LIMIT_EXAMPLE_ROWS = 100

# ---------------------------------------------------------------------------
# GraphQL query - one named operation per logical query.
# Use datetime_geq / datetime_lt for time-based streams.
# Use date_geq / date_leq for day-granularity datasets (e.g. email routing).
# ---------------------------------------------------------------------------
Q_EXAMPLE_DAY = f"""
query ExampleDay($zoneTag: String!, $datetime_geq: Time!, $datetime_lt: Time!) {{
  viewer {{
    zones(filter: {{zoneTag_in: [$zoneTag]}}) {{
      exg: exampleAdaptiveGroups(
        limit: {_LIMIT_EXAMPLE_ROWS}
        filter: {{
          datetime_geq: $datetime_geq
          datetime_lt: $datetime_lt
        }}
        orderBy: [count_DESC]
      ) {{
        count
        dimensions {{ exampleDimension }}
      }}
    }}
  }}
}}
"""


def _parse_example_rows(rows: list[dict[str, Any]]) -> dict[str, int]:
    """Parse GraphQL group rows into a dimension-to-count mapping.

    Returns a dict keyed by ``exampleDimension`` value.
    """
    result: dict[str, int] = {}
    for row in rows:
        dims = row.get("dimensions") or {}
        if not isinstance(dims, dict):
            continue
        key = str(dims.get("exampleDimension") or "").strip()
        if not key:
            continue
        result[key] = result.get(key, 0) + int(row.get("count") or 0)
    return result


def fetch_example_for_bounds(
    client: CloudflareClient,
    zone_id: str,
    since_iso_z: str,
    until_iso_z: str,
) -> dict[str, Any]:
    """Fetch example analytics for a half-open UTC interval [since, until).

    Returns the normalized payload stored under the envelope ``data`` key.
    Raise CloudflareAPIError or CloudflareRateLimitError on failure -
    do not catch those here; the sync orchestrator handles them.
    """
    vars_gql = {
        "zoneTag": zone_id,
        "datetime_geq": since_iso_z,
        "datetime_lt": until_iso_z,
    }
    raw = client.graphql(Q_EXAMPLE_DAY, vars_gql)

    # Navigate the GraphQL response envelope.
    zones = (raw.get("viewer") or {}).get("zones") or []
    zone = zones[0] if zones else {}
    rows = zone.get("exg") or []

    by_dimension = _parse_example_rows(rows)
    total_count = sum(by_dimension.values())

    return {
        "total_count": total_count,
        "by_example_dimension": [
            {"value": k, "count": v} for k, v in sorted(by_dimension.items(), key=lambda x: -x[1])
        ],
        # Add a stable payload_kind so aggregators can validate the schema.
        "payload_kind": "example_groups",
    }


def fetch_example_for_date(
    client: CloudflareClient,
    zone_id: str,
    day: date,
) -> dict[str, Any]:
    """Fetch example analytics for a full UTC calendar day.

    Wraps ``fetch_example_for_bounds`` and attaches the ``date`` key.
    """
    geq, lt = day_bounds_utc(day)
    payload = fetch_example_for_bounds(client, zone_id, geq, lt)
    payload["date"] = format_ymd(day)
    return payload


class ExampleFetcher:
    """Fetcher for the example data stream.

    Replace this docstring with a one-sentence description of what
    Cloudflare API this stream wraps (e.g. "Email routing analytics via
    emailRoutingAdaptiveGroups.").
    """

    stream_id: ClassVar[str] = "example"
    cache_filename: ClassVar[str] = "example.json"
    collect_label: ClassVar[str] = "Example"
    required_permissions: ClassVar[tuple[str, ...]] = (
        "Zone > Zone Read",
        "Zone > Analytics Read",
    )

    def outside_retention(self, day: date, *, plan_legacy_id: str | None) -> bool:
        """True if this calendar day is outside the API retention window."""
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
        """Fetch payload stored under envelope ``data`` for this UTC day."""
        _ = zone_meta
        return fetch_example_for_date(client, zone_id, day)

    def append_live_today(
        self,
        client: CloudflareClient,
        zone_id: str,
        zone_name: str,
        *,
        plan_legacy_id: str | None,
        zone_meta: dict[str, Any] | None,
    ) -> tuple[list[dict[str, Any]], list[str], bool]:
        """Partial-day fetch for the current UTC date (report only).

        Returns (extra_day_payloads, warnings, rate_limited).

        If your stream does not support partial-day data, return:
            return [], [], False
        """
        _ = (plan_legacy_id, zone_meta)
        t = utc_today()
        if date_outside_http_retention(t):
            return [], [], False
        try:
            payload = fetch_example_for_bounds(
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
                    "example analytics may be incomplete until the day finishes."
                ],
                False,
            )
        except CloudflareRateLimitError:
            return (
                [],
                [f"Could not fetch today's example data for zone {zone_name} (rate limited)."],
                True,
            )
        except CloudflareAPIError as e:
            return (
                [],
                [f"Could not fetch today's example data for zone {zone_name}: {e}"],
                False,
            )
