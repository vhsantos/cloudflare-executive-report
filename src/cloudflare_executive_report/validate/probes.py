"""Minimal API probes - one lightweight call per Cloudflare permission.

Each probe performs the cheapest possible API call that exercises the target
permission. A probe raises an exception on failure and returns any value on
success. Callers interpret exceptions, not return values.

Probe signature: (client, target_id: str) -> Any
  - Zone-scoped probes: target_id = zone_id
  - Account-scoped probes: target_id = account_id
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from cloudflare_executive_report.cf_client import CloudflareClient

# ---------------------------------------------------------------------------
# Zone-scoped probes
# ---------------------------------------------------------------------------


def probe_zone_read(client: CloudflareClient, zone_id: str) -> Any:
    """Probe Zone > Zone Read - fetch zone metadata by ID."""
    return client.get_zone(zone_id)


def probe_zone_analytics_read(client: CloudflareClient, zone_id: str) -> Any:
    """Probe Zone > Analytics Read - minimal GraphQL query (limit 1, no real data)."""
    today = datetime.now(UTC).date()
    yesterday = today - timedelta(days=1)

    # Format as YYYY-MM-DD - the only format Cloudflare accepts for Date scalars.
    date_geq = str(yesterday)  # e.g. "2026-04-19"
    date_lt = str(today)  # e.g. "2026-04-20"

    query = """
    query ProbeAnalyticsRead($zoneTag: String!, $date_geq: Date!, $date_lt: Date!) {
      viewer {
        zones(filter: {zoneTag: $zoneTag}) {
          httpRequests1dGroups(limit: 1, filter: {date_geq: $date_geq, date_lt: $date_lt}) {
            sum { requests }
          }
        }
      }
    }
    """
    return client.graphql(query, {"zoneTag": zone_id, "date_geq": date_geq, "date_lt": date_lt})


def probe_zone_dns_read(client: CloudflareClient, zone_id: str) -> Any:
    """Probe Zone > DNS Read - list at most one DNS record."""
    return client.sdk.dns.records.list(zone_id=zone_id, per_page=1)


def probe_zone_ssl_read(client: CloudflareClient, zone_id: str) -> Any:
    """Probe Zone > SSL and Certificates Read - fetch universal SSL settings."""
    return client.sdk.ssl.universal.settings.get(zone_id=zone_id)


def probe_zone_settings_read(client: CloudflareClient, zone_id: str) -> Any:
    """Probe Zone > Zone Settings Read - fetch a single lightweight zone setting."""
    return client.sdk.zones.settings.get(zone_id=zone_id, setting_id="always_use_https")


def probe_zone_firewall_read(client: CloudflareClient, zone_id: str) -> Any:
    """Probe Zone > Firewall Services Read - list zone-level rulesets."""
    return client.sdk.rulesets.list(zone_id=zone_id)


def probe_zone_waf_read(client: CloudflareClient, zone_id: str) -> Any:
    """Probe Zone > WAF Read - list managed rulesets for the zone.

    The SDK's rulesets.list() does not accept a `kind` positional filter;
    we pass it as an extra query parameter instead.
    """
    return client.sdk.rulesets.list(zone_id=zone_id, extra_query={"kind": "managed"})


def probe_zone_dns_write(client: CloudflareClient, zone_id: str) -> Any:
    """Probe for Zone > DNS Write (unwanted).

    Attempts to create a DNS record with intentionally invalid content (500.500.500.500).
    We expect a 403 if correctly read-only, or a 400 (validation error) if write access exists.
    """
    return client.sdk.dns.records.create(
        zone_id=zone_id,
        name="cf-report-write-probe",
        type="A",
        content="500.500.500.500",
        ttl=3600,
    )


# ---------------------------------------------------------------------------
# Account-scoped probes
# ---------------------------------------------------------------------------


def probe_account_rulesets_read(client: CloudflareClient, account_id: str) -> Any:
    """Probe Account > Account Rulesets Read - list account-level rulesets."""
    return client.sdk.rulesets.list(account_id=account_id)


def probe_account_analytics_read(client: CloudflareClient, account_id: str) -> Any:
    """Probe Account > Account Analytics Read - minimal account-level GraphQL query."""
    today = datetime.now(UTC).date()
    yesterday = today - timedelta(days=1)

    # Format as YYYY-MM-DD - the only format Cloudflare accepts for Date scalars.
    date_geq = str(yesterday)  # e.g. "2026-04-19"
    date_lt = str(today)  # e.g. "2026-04-20"

    query = """
    query ProbeAccountAnalyticsRead($accountTag: String!, $date_geq: Date!, $date_lt: Date!) {
      viewer {
        accounts(filter: {accountTag: $accountTag}) {
          httpRequests1dGroups(limit: 1, filter: {date_geq: $date_geq, date_lt: $date_lt}) {
            sum { requests }
          }
        }
      }
    }
    """
    return client.graphql(
        query, {"accountTag": account_id, "date_geq": date_geq, "date_lt": date_lt}
    )


def probe_account_audit_read(client: CloudflareClient, account_id: str) -> Any:
    """Probe Account > Access: Audit Logs Read - fetch at most one recent audit log.

    Uses a 30-second window anchored at now so the query is always structurally
    valid regardless of how far back Cloudflare retains audit logs.
    """
    now = datetime.now(UTC)
    since = (now - timedelta(seconds=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    before = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    return client.list_account_audit_logs(
        account_id,
        since=since,
        before=before,
        limit=1,
    )


def probe_account_settings_read(client: CloudflareClient, account_id: str) -> Any:
    """Probe Account > Account Settings Read - fetch account details."""
    return client.sdk.accounts.get(account_id=account_id)
