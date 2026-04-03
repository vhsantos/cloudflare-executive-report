"""Registered fetchers: single place to add a new dataset."""

from __future__ import annotations

from pathlib import Path

from cloudflare_executive_report.fetchers.dns import DnsFetcher
from cloudflare_executive_report.fetchers.http import HttpFetcher
from cloudflare_executive_report.fetchers.security import SecurityFetcher
from cloudflare_executive_report.fetchers.types import Fetcher

# Order preserved: sync and report iterate in this order.
FETCHER_REGISTRY: dict[str, Fetcher] = {
    "dns": DnsFetcher(),
    "http": HttpFetcher(),
    "security": SecurityFetcher(),
}


def registered_stream_ids() -> tuple[str, ...]:
    return tuple(FETCHER_REGISTRY.keys())


def default_types_csv() -> str:
    return ",".join(FETCHER_REGISTRY.keys())


def day_cache_path(cache_root: Path, zone_id: str, day_yyyy_mm_dd: str, stream_id: str) -> Path:
    fn = FETCHER_REGISTRY[stream_id].cache_filename
    return cache_root / zone_id / day_yyyy_mm_dd / fn
