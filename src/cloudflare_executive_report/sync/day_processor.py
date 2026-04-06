"""Generic per-day cache fill for any registered fetcher."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from cloudflare_executive_report.cache import read_day_file, write_day_file
from cloudflare_executive_report.cf_client import (
    CloudflareAPIError,
    CloudflareClient,
    CloudflareRateLimitError,
)
from cloudflare_executive_report.dates import format_ymd
from cloudflare_executive_report.fetchers.registry import day_cache_path
from cloudflare_executive_report.fetchers.types import Fetcher


def _progress(msg: str, *, quiet: bool) -> None:
    if not quiet:
        print(msg, flush=True)


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
    force_fetch: bool,
    refresh: bool,
    quiet: bool,
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
        _progress(f"  {zone_name} {ds} {name} outside retention (cached null)", quiet=quiet)
        return False

    cached = read_day_file(path)
    if not force_fetch and not should_refetch_cached(cached, refresh):
        _progress(f"  {zone_name} {ds} {name} skip (cached)", quiet=quiet)
        return False

    try:
        data = fetcher.fetch(client, zone_id, day)
        write_day_file(path, source="api", data=data)
        _progress(f"  {zone_name} {ds} {name} ok", quiet=quiet)
        return False
    except CloudflareRateLimitError as e:
        write_day_file(
            path,
            source="error",
            data=None,
            error=str(e),
            retry_after=e.retry_after,
        )
        _progress(f"  {zone_name} {ds} {name} rate-limited", quiet=quiet)
        return True
    except CloudflareAPIError as e:
        write_day_file(path, source="error", data=None, error=str(e))
        _progress(f"  {zone_name} {ds} {name} error", quiet=quiet)
        return False
