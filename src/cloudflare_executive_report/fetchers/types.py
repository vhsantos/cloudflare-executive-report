"""Fetcher protocol for cache sync and optional live-today append."""

from __future__ import annotations

from datetime import date
from typing import Any, ClassVar, Protocol, runtime_checkable

from cloudflare_executive_report.cf_client import CloudflareClient


@runtime_checkable
class Fetcher(Protocol):
    stream_id: ClassVar[str]
    cache_filename: ClassVar[str]
    collect_label: ClassVar[str]

    def outside_retention(self, day: date, *, plan_legacy_id: str | None) -> bool:
        """True if this calendar day is outside the API retention window."""

    def fetch(self, client: CloudflareClient, zone_id: str, day: date) -> Any:
        """Fetch payload stored under envelope `data` for this UTC day."""

    def append_live_today(
        self,
        client: CloudflareClient,
        zone_id: str,
        zone_name: str,
        *,
        plan_legacy_id: str | None,
    ) -> tuple[list[dict[str, Any]], list[str], bool]:
        """
        Optional partial-day fetch for the current UTC date (report only).
        Returns (extra_day_payloads, warnings, rate_limited).
        """
