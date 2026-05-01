"""Email routing and security analytics via GraphQL and REST API."""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, ClassVar

from cloudflare_executive_report.cf_client import (
    CloudflareAPIError,
    CloudflareAuthError,
    CloudflareClient,
    CloudflareRateLimitError,
)
from cloudflare_executive_report.common.constants import UNAVAILABLE
from cloudflare_executive_report.common.dates import (
    format_ymd,
    utc_today,
)
from cloudflare_executive_report.common.retention import date_outside_http_retention
from cloudflare_executive_report.fetchers.graphql_common import (
    viewer_first_zone,
    zone_alias_groups,
)

log = logging.getLogger(__name__)

_LIMIT_ERG_ROWS = 1000
_LIMIT_DMARC_TOP = 20

Q_EMAIL_DAY = f"""
query EmailRoutingDay($zoneTag: String!, $since: String!, $until: String!) {{
  viewer {{
    zones(filter: {{ zoneTag_in: [$zoneTag] }}) {{
      erg: emailRoutingAdaptiveGroups(
        limit: {_LIMIT_ERG_ROWS}
        filter: {{ date_geq: $since, date_leq: $until }}
      ) {{
        count
        dimensions {{
          action
          status
        }}
      }}
      erg_dmarc: dmarcReportsSourcesAdaptiveGroups(
        limit: {_LIMIT_ERG_ROWS}
        filter: {{ date_geq: $since, date_leq: $until }}
      ) {{
        sum {{
          totalMatchingMessages
          dkimPass
          spfPass
          dmarc
        }}
      }}
      erg_dmarc_top: dmarcReportsSourcesAdaptiveGroups(
        limit: {_LIMIT_DMARC_TOP}
        filter: {{ date_geq: $since, date_leq: $until }}
      ) {{
        sum {{
          totalMatchingMessages
          dkimPass
          spfPass
          dmarc
        }}
        dimensions {{
          sourceOrgName
        }}
      }}
    }}
  }}
}}
"""


def _parse_dns_policies(
    client: CloudflareClient, zone_id: str, zone_name: str
) -> tuple[str, str, bool]:
    """Parse DMARC, SPF, and DKIM policies from DNS records.

    DKIM can be configured via:
    - TXT records (self-hosted DKIM)
    - CNAME records (Microsoft 365, Google Workspace, etc.)
    """
    dmarc_policy = "none"
    spf_policy = "none"
    dkim_configured = False

    if not zone_name:
        log.warning("zone_name is empty for zone_id=%s; DNS policy check skipped", zone_id)
        return UNAVAILABLE, UNAVAILABLE, False

    try:
        # Fetch BOTH TXT and CNAME records
        txt_records = client.list_dns_records(zone_id, per_page=500, record_type="TXT")
        cname_records = client.list_dns_records(zone_id, per_page=500, record_type="CNAME")
        all_records = txt_records + cname_records
    except Exception as e:
        log.debug("Failed to list DNS records for email policies: %s", e)
        return UNAVAILABLE, UNAVAILABLE, False

    for rec in all_records:
        name = str(rec.get("name") or "").strip().lower()
        content = str(rec.get("content") or "").strip().lower().strip('"')
        record_type = str(rec.get("type") or "").upper()

        # DMARC (always TXT)
        if (
            record_type == "TXT"
            and name == f"_dmarc.{zone_name}"
            and content.startswith("v=dmarc1")
        ):
            # e.g., "v=DMARC1; p=reject; ..."
            parts = content.split(";")
            for part in parts:
                part = part.strip()
                if part.startswith("p="):
                    dmarc_policy = part[2:].strip()
                    break

        # SPF (always TXT)
        elif record_type == "TXT" and name == zone_name and content.startswith("v=spf1"):
            # e.g., "v=spf1 include:_spf.mx.cloudflare.net ~all"
            if "-all" in content:
                spf_policy = "hardfail"
            elif "~all" in content:
                spf_policy = "softfail"
            elif "?all" in content:
                spf_policy = "neutral"
            elif "+all" in content:
                spf_policy = "allow"
            else:
                spf_policy = "custom"

        # DKIM - Check both TXT and CNAME
        elif name.endswith(f"._domainkey.{zone_name}"):
            if record_type == "TXT" and content.startswith("v=dkim1"):
                # Self-hosted DKIM (TXT record with public key)
                dkim_configured = True
            elif record_type == "CNAME":
                # Provider-managed DKIM (Microsoft 365, Google Workspace, etc.)
                # CNAME points to provider's DKIM key
                dkim_configured = True

    return dmarc_policy, spf_policy, dkim_configured


def fetch_email_for_bounds(
    client: CloudflareClient,
    zone_id: str,
    zone_name: str,
    since: str,
    until: str,
) -> dict[str, Any]:
    """Fetch email routing analytics and DNS policies for a time range."""
    vars_gql = {
        "zoneTag": zone_id,
        "since": since,
        "until": until,
    }
    raw = client.graphql(Q_EMAIL_DAY, vars_gql)
    zone = viewer_first_zone(raw)

    erg_rows = zone_alias_groups(zone, "erg")
    erg_dmarc_rows = zone_alias_groups(zone, "erg_dmarc")
    erg_dmarc_top_rows = zone_alias_groups(zone, "erg_dmarc_top")

    erg_metrics = []
    for row in erg_rows:
        dims = row.get("dimensions") or {}
        if not isinstance(dims, dict):
            continue
        erg_metrics.append(
            {
                "action": str(dims.get("action") or ""),
                "status": str(dims.get("status") or ""),
                "count": int(row.get("count") or 0),
            }
        )

    erg_dmarc_metrics = []
    for row in erg_dmarc_rows:
        sums = row.get("sum") or {}
        if not isinstance(sums, dict):
            continue
        erg_dmarc_metrics.append(
            {
                "totalMatchingMessages": int(sums.get("totalMatchingMessages") or 0),
                "dkimPass": int(sums.get("dkimPass") or 0),
                "spfPass": int(sums.get("spfPass") or 0),
                "dmarc": int(sums.get("dmarc") or 0),
            }
        )

    erg_dmarc_top_sources = []
    for row in erg_dmarc_top_rows:
        dims = row.get("dimensions") or {}
        if not isinstance(dims, dict):
            continue
        sums = row.get("sum") or {}
        if not isinstance(sums, dict):
            continue
        erg_dmarc_top_sources.append(
            {
                "sourceOrgName": str(dims.get("sourceOrgName") or ""),
                "totalMatchingMessages": int(sums.get("totalMatchingMessages") or 0),
                "dkimPass": int(sums.get("dkimPass") or 0),
                "spfPass": int(sums.get("spfPass") or 0),
                "dmarc": int(sums.get("dmarc") or 0),
            }
        )

    # Fetch settings
    settings = client.get_email_routing_settings(zone_id)
    enabled = bool(settings.get("enabled"))
    status = str(settings.get("status") or UNAVAILABLE).lower()

    # Fetch rules count only if ER is enabled
    rules_count = 0
    if enabled:
        try:
            rules = client.list_email_routing_rules(zone_id)
            # Only count active rules
            rules_count = sum(1 for r in rules if r.get("enabled") is True)
        except (CloudflareAPIError, CloudflareAuthError) as e:
            log.debug("Failed to fetch email routing rules: %s", e)

    dmarc_policy, spf_policy, dkim_configured = _parse_dns_policies(client, zone_id, zone_name)

    return {
        "email_routing_enabled": enabled,
        "email_routing_status": status,
        "routing_rules_count": rules_count,
        "dns_dmarc_policy": dmarc_policy,
        "dns_spf_policy": spf_policy,
        "dns_dkim_configured": dkim_configured,
        "erg_metrics": erg_metrics,
        "erg_dmarc_metrics": erg_dmarc_metrics,
        "erg_dmarc_top_sources": erg_dmarc_top_sources,
        "payload_kind": "email_routing_groups",
    }


def fetch_email_for_date(
    client: CloudflareClient,
    zone_id: str,
    zone_name: str,
    day: date,
) -> dict[str, Any]:
    """Fetch email routing analytics for a full UTC calendar day."""
    ds = format_ymd(day)
    payload = fetch_email_for_bounds(client, zone_id, zone_name, ds, ds)
    payload["date"] = ds
    return payload


class EmailFetcher:
    """Email routing and security analytics via GraphQL and REST API."""

    stream_id: ClassVar[str] = "email"
    cache_filename: ClassVar[str] = "email.json"
    collect_label: ClassVar[str] = "Email"
    required_permissions: ClassVar[tuple[str, ...]] = (
        "Zone > Zone Read",
        "Zone > Analytics Read",
        "Zone > Email Routing Rules Read",
        "Zone > Email Security DMARC Reports Read",
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
        """Fetch payload for this UTC day."""
        zone_name = str((zone_meta or {}).get("name") or "").strip().lower()
        return fetch_email_for_date(client, zone_id, zone_name, day)

    def append_live_today(
        self,
        client: CloudflareClient,
        zone_id: str,
        zone_name: str,
        *,
        plan_legacy_id: str | None,
        zone_meta: dict[str, Any] | None,
    ) -> tuple[list[dict[str, Any]], list[str], bool]:
        """Partial-day fetch for the current UTC date (report only)."""
        _ = (plan_legacy_id, zone_meta)
        t = utc_today()
        if date_outside_http_retention(t):
            return [], [], False
        try:
            # We use YYYY-MM-DD for date_geq and the next day for date_lt
            # to get today's data in the GraphQL date_ filter.
            ds = format_ymd(t)
            payload = fetch_email_for_bounds(client, zone_id, zone_name, ds, ds)
            payload["date"] = ds
            return (
                [payload],
                [
                    "Report includes today's UTC date; "
                    "email analytics may be incomplete until the day finishes."
                ],
                False,
            )
        except CloudflareRateLimitError:
            return (
                [],
                [f"Could not fetch today's email data for zone {zone_name} (rate limited)."],
                True,
            )
        except CloudflareAPIError as e:
            return (
                [],
                [f"Could not fetch today's email data for zone {zone_name}: {e}"],
                False,
            )
