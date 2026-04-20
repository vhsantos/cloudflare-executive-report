"""Generic per-day cache fill for any registered fetcher."""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import Any

from cloudflare_executive_report.cache import read_day_file, write_day_file
from cloudflare_executive_report.cf_client import (
    CloudflareAPIError,
    CloudflareClient,
    CloudflareRateLimitError,
)
from cloudflare_executive_report.common.dates import format_ymd
from cloudflare_executive_report.fetchers.registry import day_cache_path
from cloudflare_executive_report.fetchers.types import Fetcher


def should_refetch_cached(cached: dict | None, refresh: bool) -> bool:
    if refresh:
        return True
    if cached is None:
        return True
    src = cached.get("_source")
    if src == "error":
        return True
    if src == "null":
        return False
    return False


def process_day(
    fetcher: Fetcher,
    client: CloudflareClient,
    cache_root: Path,
    zone_id: str,
    zone_name: str,
    day: date,
    *,
    plan_legacy_id: str | None,
    zone_meta: dict[str, Any] | None,
    force_fetch: bool,
    refresh: bool,
) -> bool:
    """
    Fetch one day into cache for this stream.
    Returns True if rate limited after retries.
    """
    ds = format_ymd(day)
    path = day_cache_path(cache_root, zone_id, ds, fetcher.stream_id)
    name = fetcher.stream_id

    if fetcher.outside_retention(day, plan_legacy_id=plan_legacy_id):
        write_day_file(path, source="null", data=None)
        logging.debug("  %s %s %s outside retention (cached null)", zone_name, ds, name)
        return False

    cached = read_day_file(path)
    if not force_fetch and not should_refetch_cached(cached, refresh):
        logging.debug("  %s %s %s skip (cached)", zone_name, ds, name)
        return False

    try:
        data = fetcher.fetch(client, zone_id, day, zone_meta=zone_meta)
        write_day_file(path, source="api", data=data)
        logging.info("  %s %s %s ok", zone_name, ds, name)
        return False
    except CloudflareRateLimitError as e:
        write_day_file(
            path,
            source="error",
            data=None,
            error=str(e),
            retry_after=e.retry_after,
        )
        logging.warning("  %s %s %s rate-limited", zone_name, ds, name)
        return True
    except CloudflareAPIError as e:
        write_day_file(path, source="error", data=None, error=str(e))
        logging.warning("  %s %s %s error: %s", zone_name, ds, name, e)
        return False
