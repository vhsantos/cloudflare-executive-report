"""DNS records inventory snapshot (SDK, optional/permission-gated)."""

from __future__ import annotations

from datetime import date
from typing import Any, ClassVar

from cloudflare_executive_report.cf_client import (
    CloudflareAPIError,
    CloudflareAuthError,
    CloudflareClient,
)
from cloudflare_executive_report.dates import format_ymd, utc_today


def _type_counts(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for r in records:
        t = str(r.get("type") or "").strip().upper()
        if not t:
            continue
        counts[t] = counts.get(t, 0) + 1
    return [{"value": k, "count": v} for k, v in sorted(counts.items(), key=lambda x: -x[1])]


def _fetch_all_dns_records(client: CloudflareClient, zone_id: str) -> list[dict[str, Any]]:
    rows = client.list_dns_records(zone_id, per_page=100)
    return [r for r in rows if isinstance(r, dict)]


def fetch_dns_records_snapshot(client: CloudflareClient, zone_id: str, day: date) -> dict[str, Any]:
    try:
        zone = client.get_zone(zone_id)
        zone_name = str(zone.get("name") or "").strip().lower()
        rows = _fetch_all_dns_records(client, zone_id)
    except CloudflareAuthError:
        return {
            "date": format_ymd(day),
            "unavailable": True,
            "reason": "permission_denied",
        }
    except CloudflareAPIError as e:
        return {
            "date": format_ymd(day),
            "unavailable": True,
            "reason": f"api_error:{e}",
        }

    proxied = 0
    dns_only = 0
    apex_unproxied = 0
    for r in rows:
        p = r.get("proxied")
        if p is True:
            proxied += 1
        elif p is False:
            dns_only += 1
        rtype = str(r.get("type") or "").strip().upper()
        name = str(r.get("name") or "").strip().lower()
        if name == zone_name and rtype in {"A", "AAAA"} and p is False:
            apex_unproxied += 1

    return {
        "date": format_ymd(day),
        "total_records": len(rows),
        "proxied_records": proxied,
        "dns_only_records": dns_only,
        "apex_unproxied_a_aaaa": apex_unproxied,
        "record_types": _type_counts(rows),
    }


class DnsRecordsFetcher:
    stream_id: ClassVar[str] = "dns_records"
    cache_filename: ClassVar[str] = "dns_records.json"
    collect_label: ClassVar[str] = "DNS records"

    def outside_retention(self, day: date, *, plan_legacy_id: str | None) -> bool:
        _ = (day, plan_legacy_id)
        return False

    def fetch(self, client: CloudflareClient, zone_id: str, day: date) -> dict[str, Any]:
        return fetch_dns_records_snapshot(client, zone_id, day)

    def append_live_today(
        self,
        client: CloudflareClient,
        zone_id: str,
        zone_name: str,
        *,
        plan_legacy_id: str | None,
    ) -> tuple[list[dict[str, Any]], list[str], bool]:
        _ = (zone_name, plan_legacy_id)
        return [fetch_dns_records_snapshot(client, zone_id, utc_today())], [], False
