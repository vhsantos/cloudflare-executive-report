"""Certificate snapshot (SDK, optional/permission-gated)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any, ClassVar

from cloudflare_executive_report.cf_client import (
    CloudflareAPIError,
    CloudflareAuthError,
    CloudflareClient,
)
from cloudflare_executive_report.dates import format_ymd, utc_today


def _parse_dt(v: Any) -> datetime | None:
    s = str(v or "").strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(s).astimezone(UTC)
    except ValueError:
        return None


def fetch_certificates_snapshot(
    client: CloudflareClient, zone_id: str, day: date
) -> dict[str, Any]:
    try:
        packs = client.list_zone_certificate_packs(zone_id)
    except CloudflareAuthError:
        return {"date": format_ymd(day), "unavailable": True, "reason": "permission_denied"}
    except CloudflareAPIError as e:
        return {"date": format_ymd(day), "unavailable": True, "reason": f"api_error:{e}"}

    now = datetime.now(UTC)
    expiring_packs_30 = 0
    soonest_expiry: datetime | None = None
    status_counts: dict[str, int] = {}

    for pack in packs:
        status = str(pack.get("status") or "unknown").strip() or "unknown"
        status_counts[status] = status_counts.get(status, 0) + 1

        certificates = pack.get("certificates") or []
        if not certificates:
            continue
        primary_cert = certificates[0]
        expiry = _parse_dt(primary_cert.get("expires_on"))
        if expiry is None:
            continue

        if soonest_expiry is None or expiry < soonest_expiry:
            soonest_expiry = expiry
        if (expiry - now).days <= 30:
            expiring_packs_30 += 1

    return {
        "date": format_ymd(day),
        "total_certificate_packs": len(packs),
        "expiring_in_30_days": expiring_packs_30,
        "soonest_expiry": soonest_expiry.strftime("%Y-%m-%dT%H:%M:%SZ") if soonest_expiry else None,
        "status_breakdown": [{"value": k, "count": c} for k, c in sorted(status_counts.items())],
    }


class CertificatesFetcher:
    stream_id: ClassVar[str] = "certificates"
    cache_filename: ClassVar[str] = "certificates.json"
    collect_label: ClassVar[str] = "Certificates"

    def outside_retention(self, day: date, *, plan_legacy_id: str | None) -> bool:
        _ = (day, plan_legacy_id)
        return False

    def fetch(
        self,
        client: CloudflareClient,
        zone_id: str,
        day: date,
        *,
        zone_meta: dict[str, Any] | None,
    ) -> dict[str, Any]:
        _ = zone_meta
        return fetch_certificates_snapshot(client, zone_id, day)

    def append_live_today(
        self,
        client: CloudflareClient,
        zone_id: str,
        zone_name: str,
        *,
        plan_legacy_id: str | None,
        zone_meta: dict[str, Any] | None,
    ) -> tuple[list[dict[str, Any]], list[str], bool]:
        _ = (zone_name, plan_legacy_id, zone_meta)
        t = utc_today()
        return [fetch_certificates_snapshot(client, zone_id, t)], [], False
