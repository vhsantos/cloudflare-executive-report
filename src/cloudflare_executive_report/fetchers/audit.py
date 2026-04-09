"""Account audit-log snapshot (REST, optional/permission-gated)."""

from __future__ import annotations

from datetime import date
from typing import Any, ClassVar

from cloudflare_executive_report.cf_client import (
    CloudflareAPIError,
    CloudflareAuthError,
    CloudflareClient,
)
from cloudflare_executive_report.common.dates import day_bounds_utc, format_ymd, utc_today


def _event_label(row: dict[str, Any]) -> str:
    action = row.get("action")
    if isinstance(action, dict):
        t = str(action.get("type") or "").strip()
        if t:
            return t
        desc = str(action.get("description") or "").strip()
        if desc:
            return desc
    return str(row.get("id") or "event").strip() or "event"


def _top_value_counts(values: list[str], *, top: int = 10) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for v in values:
        if not v:
            continue
        counts[v] = counts.get(v, 0) + 1
    return [{"value": k, "count": c} for k, c in sorted(counts.items(), key=lambda x: -x[1])[:top]]


def fetch_audit_snapshot(
    client: CloudflareClient, zone_id: str, since_iso: str, until_iso: str, day: date
) -> dict[str, Any]:
    try:
        zone = client.get_zone(zone_id)
    except CloudflareAuthError:
        return {"date": format_ymd(day), "unavailable": True, "reason": "permission_denied"}
    except CloudflareAPIError as e:
        return {"date": format_ymd(day), "unavailable": True, "reason": f"api_error:{e}"}
    return fetch_audit_snapshot_with_account(
        client,
        account_id=str((zone.get("account") or {}).get("id") or "").strip(),
        since_iso=since_iso,
        until_iso=until_iso,
        day=day,
    )


def fetch_audit_snapshot_with_account(
    client: CloudflareClient, *, account_id: str, since_iso: str, until_iso: str, day: date
) -> dict[str, Any]:
    try:
        if not account_id:
            return {"date": format_ymd(day), "unavailable": True, "reason": "missing_account_id"}
        # SDK: audit_logs.list
        rows = client.list_account_audit_logs(
            account_id,
            since=since_iso,
            before=until_iso,
            limit=100,
        )
        if not isinstance(rows, list):
            rows = []
    except CloudflareAuthError:
        return {"date": format_ymd(day), "unavailable": True, "reason": "permission_denied"}
    except CloudflareAPIError as e:
        return {"date": format_ymd(day), "unavailable": True, "reason": f"api_error:{e}"}

    actor_values: list[str] = []
    action_values: list[str] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        actor = r.get("actor") or {}
        if isinstance(actor, dict):
            actor_values.append(str(actor.get("email") or actor.get("id") or "").strip())
        action_values.append(_event_label(r))
    return {
        "date": format_ymd(day),
        "total_events": len(rows),
        "top_actions": _top_value_counts(action_values),
        "top_actors": _top_value_counts(actor_values),
    }


class AuditFetcher:
    stream_id: ClassVar[str] = "audit"
    cache_filename: ClassVar[str] = "audit.json"
    collect_label: ClassVar[str] = "Audit logs"

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
        since, until = day_bounds_utc(day)
        if zone_meta:
            account_id = str(((zone_meta.get("account") or {}).get("id")) or "").strip()
            return fetch_audit_snapshot_with_account(
                client, account_id=account_id, since_iso=since, until_iso=until, day=day
            )
        return fetch_audit_snapshot(client, zone_id, since, until, day)

    def append_live_today(
        self,
        client: CloudflareClient,
        zone_id: str,
        zone_name: str,
        *,
        plan_legacy_id: str | None,
        zone_meta: dict[str, Any] | None,
    ) -> tuple[list[dict[str, Any]], list[str], bool]:
        _ = (zone_name, plan_legacy_id)
        t = utc_today()
        return (
            [self.fetch(client, zone_id, t, zone_meta=zone_meta)],
            [],
            False,
        )
