"""Zone helpers (REST via CloudflareClient / official SDK)."""

from __future__ import annotations

from typing import Any

from cloudflare_executive_report.cf_client import CloudflareClient


def list_all_zones(client: CloudflareClient) -> list[dict[str, Any]]:
    return client.list_zones()


def get_zone(client: CloudflareClient, zone_id: str) -> dict[str, Any]:
    return client.get_zone(zone_id)


def find_zone_by_name(client: CloudflareClient, name: str) -> dict[str, Any] | None:
    return client.find_zone_by_name(name)
