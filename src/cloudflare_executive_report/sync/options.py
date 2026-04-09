from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class SyncMode(StrEnum):
    incremental = "incremental"
    last_n = "last_n"
    range = "range"
    last_month = "last_month"
    last_week = "last_week"
    last_year = "last_year"
    this_month = "this_month"
    this_week = "this_week"
    this_year = "this_year"
    yesterday = "yesterday"


def _default_sync_types() -> frozenset[str]:
    from cloudflare_executive_report.fetchers.registry import registered_stream_ids

    return frozenset(registered_stream_ids())


@dataclass
class SyncOptions:
    mode: SyncMode
    last_n: int | None = None
    start: str | None = None
    end: str | None = None
    refresh: bool = False
    include_today: bool = False
    quiet: bool = False
    types: frozenset[str] = field(default_factory=_default_sync_types)
    top: int = 10
    skip_zone_health: bool = False
