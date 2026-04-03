"""Sync DNS cache and build report."""

from __future__ import annotations

import json
import logging
import shutil
import sys
from dataclasses import dataclass
from datetime import timedelta
from enum import StrEnum
from pathlib import Path

from cloudflare_executive_report import exits
from cloudflare_executive_report.aggregate import (
    build_dns_section,
    build_report,
    collect_days_payloads,
)
from cloudflare_executive_report.cache import (
    CacheLockTimeout,
    cache_lock,
    load_zone_index,
    merge_index_bounds,
    read_dns_cache,
    save_zone_index,
    write_dns_cache,
)
from cloudflare_executive_report.cf_client import (
    CloudflareAPIError,
    CloudflareAuthError,
    CloudflareClient,
    CloudflareRateLimitError,
)
from cloudflare_executive_report.config import AppConfig
from cloudflare_executive_report.dates import (
    day_bounds_utc,
    format_ymd,
    iter_dates_inclusive,
    last_n_complete_days,
    parse_ymd,
    utc_today,
    utc_yesterday,
)
from cloudflare_executive_report.dns_fetch import fetch_dns_day
from cloudflare_executive_report.retention import (
    date_outside_dns_retention,
    dns_retention_days,
)
from cloudflare_executive_report.zones_api import get_zone

log = logging.getLogger(__name__)


class SyncMode(StrEnum):
    incremental = "incremental"
    last_n = "last_n"
    range = "range"


@dataclass
class SyncOptions:
    mode: SyncMode
    last_n: int | None = None
    start: str | None = None
    end: str | None = None
    refresh: bool = False
    include_today: bool = False
    quiet: bool = False


def _progress(msg: str, *, quiet: bool) -> None:
    if not quiet:
        print(msg, flush=True)


def _dates_incremental(idx_dns_latest: str | None, y) -> list:
    if idx_dns_latest:
        latest = parse_ymd(idx_dns_latest)
    else:
        latest = y
    out = []
    d = latest + timedelta(days=1)
    while d <= y:
        out.append(d)
        d += timedelta(days=1)
    return out


def _should_fetch_incremental(cached: dict | None, refresh: bool) -> bool:
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


def _process_day(
    *,
    client: CloudflareClient,
    cache_root: Path,
    zone_id: str,
    zone_name: str,
    day,
    retention_days: int,
    force_fetch: bool,
    refresh: bool,
    quiet: bool,
) -> bool:
    """Returns True if rate limit hit after retries."""
    ds = format_ymd(day)
    if date_outside_dns_retention(day, retention_days):
        write_dns_cache(cache_root, zone_id, ds, source="null", data=None)
        _progress(f"  {zone_name} {ds} outside retention (cached null)", quiet=quiet)
        return False

    cached = read_dns_cache(cache_root, zone_id, ds)
    if not force_fetch and not _should_fetch_incremental(cached, refresh):
        _progress(f"  {zone_name} {ds} skip (cached)", quiet=quiet)
        return False

    ge, lt = day_bounds_utc(day)
    try:
        data = fetch_dns_day(client, zone_id, ge, lt)
        write_dns_cache(cache_root, zone_id, ds, source="api", data=data)
        _progress(f"  {zone_name} {ds} ok", quiet=quiet)
        return False
    except CloudflareRateLimitError as e:
        write_dns_cache(
            cache_root,
            zone_id,
            ds,
            source="error",
            data=None,
            error=str(e),
            retry_after=e.retry_after,
        )
        return True
    except CloudflareAPIError as e:
        write_dns_cache(
            cache_root,
            zone_id,
            ds,
            source="error",
            data=None,
            error=str(e),
        )
        return False


def run_sync(
    cfg: AppConfig,
    opts: SyncOptions,
    *,
    zone_filter: str | None = None,
    output_path: Path | None = None,
    write_stdout: bool = False,
) -> int:
    cache_root = cfg.cache_path()
    zones = list(cfg.zones)
    if zone_filter:
        zf = zone_filter.strip()
        zones = [z for z in zones if z.id == zf or z.name == zf]
        if not zones:
            log.error("Zone not found in config: %s", zone_filter)
            return exits.INVALID_PARAMS

    if not zones:
        log.error("No zones configured. Use `cf-report zones add` or set `zones` in config.")
        return exits.INVALID_PARAMS

    y = utc_yesterday()

    try:
        with cache_lock(cache_root):
            return _run_sync_locked(
                cfg,
                opts,
                zones,
                cache_root,
                y,
                output_path=output_path,
                write_stdout=write_stdout,
            )
    except CacheLockTimeout as e:
        log.error("%s", e)
        return exits.CACHE_LOCK_TIMEOUT


def _run_sync_locked(
    cfg: AppConfig,
    opts: SyncOptions,
    zones: list,
    cache_root: Path,
    y,
    *,
    output_path: Path | None,
    write_stdout: bool,
) -> int:
    rate_fail = False
    verbose_http = log.isEnabledFor(logging.DEBUG)

    with CloudflareClient(cfg.api_token, verbose=verbose_http) as client:
        for z in zones:
            _progress(f"Zone {z.name} ({z.id})", quiet=opts.quiet)
            try:
                zmeta = get_zone(client, z.id)
            except CloudflareAuthError as e:
                log.error("%s", e)
                return exits.AUTH_FAILED
            except CloudflareAPIError as e:
                log.error("Zone lookup failed: %s", e)
                return exits.GENERAL_ERROR

            plan = (zmeta.get("plan") or {}).get("legacy_id")
            retention = dns_retention_days(plan)

            idx = load_zone_index(cache_root, z.id, z.name)
            idx.zone_name = z.name

            force_fetch = opts.mode in (SyncMode.last_n, SyncMode.range)

            if opts.mode == SyncMode.incremental:
                days = _dates_incremental(idx.dns_latest, y)
            elif opts.mode == SyncMode.last_n:
                assert opts.last_n is not None
                d0, d1 = last_n_complete_days(opts.last_n, yesterday=y)
                days = list(iter_dates_inclusive(d0, d1))
            else:
                assert opts.start and opts.end
                d0, d1 = parse_ymd(opts.start), parse_ymd(opts.end)
                if d1 > y:
                    log.error(
                        "--end cannot be after yesterday (UTC). Use --include-today for today."
                    )
                    return exits.INVALID_PARAMS
                days = list(iter_dates_inclusive(d0, d1))

            for d in days:
                if _process_day(
                    client=client,
                    cache_root=cache_root,
                    zone_id=z.id,
                    zone_name=z.name,
                    day=d,
                    retention_days=retention,
                    force_fetch=force_fetch,
                    refresh=opts.refresh,
                    quiet=opts.quiet,
                ):
                    rate_fail = True

            new_idx = load_zone_index(cache_root, z.id, z.name)
            new_idx.zone_name = z.name
            if days:
                new_idx = merge_index_bounds(new_idx, format_ymd(min(days)), format_ymd(max(days)))
                if opts.mode == SyncMode.incremental:
                    new_idx = merge_index_bounds(new_idx, None, format_ymd(y))
            save_zone_index(cache_root, new_idx)

        if opts.mode == SyncMode.last_n and opts.last_n is not None:
            d0, d1 = last_n_complete_days(opts.last_n, yesterday=y)
            report_start, report_end = format_ymd(d0), format_ymd(d1)
        elif opts.mode == SyncMode.range and opts.start and opts.end:
            report_start = opts.start
            report_end = opts.end
        else:
            earliests: list[str] = []
            latests: list[str] = []
            for z in zones:
                ix = load_zone_index(cache_root, z.id, z.name)
                if ix.dns_earliest:
                    earliests.append(ix.dns_earliest)
                if ix.dns_latest:
                    latests.append(ix.dns_latest)
            report_start = min(earliests) if earliests else format_ymd(y)
            report_end = max(latests) if latests else format_ymd(y)

        requested_start, requested_end = report_start, report_end
        if opts.include_today:
            report_end = format_ymd(utc_today())
            requested_end = report_end

        zones_out: list[dict] = []
        all_warnings: list[str] = []

        for z in zones:
            try:
                zmeta = get_zone(client, z.id)
            except CloudflareAuthError as e:
                log.error("%s", e)
                return exits.AUTH_FAILED
            except CloudflareAPIError as e:
                log.error("Zone lookup failed: %s", e)
                return exits.GENERAL_ERROR
            plan = (zmeta.get("plan") or {}).get("legacy_id")
            retention = dns_retention_days(plan)

            def reader(zi: str, ds: str) -> dict | None:
                return read_dns_cache(cache_root, zi, ds)

            cache_end = format_ymd(y) if opts.include_today else report_end
            api_days, warns = collect_days_payloads(reader, z.id, z.name, report_start, cache_end)

            if opts.include_today:
                t = utc_today()
                if not date_outside_dns_retention(t, retention):
                    ge, lt = day_bounds_utc(t)
                    try:
                        td = fetch_dns_day(client, z.id, ge, lt)
                        api_days = api_days + [td]
                        warns.append(
                            "Report includes today's UTC date; "
                            "DNS data may be incomplete until the day finishes."
                        )
                    except CloudflareRateLimitError:
                        rate_fail = True
                        warns.append(
                            f"Could not fetch today's DNS data for zone {z.name} (rate limited)."
                        )
                    except CloudflareAPIError as e:
                        warns.append(f"Could not fetch today's DNS data for zone {z.name}: {e}")

            dns_block = build_dns_section(api_days)
            zones_out.append({"zone_id": z.id, "zone_name": z.name, "dns": dns_block})
            all_warnings.extend(warns)

        rep = build_report(
            zones_out=zones_out,
            warnings=all_warnings,
            period_start=report_start,
            period_end=report_end,
            requested_start=requested_start,
            requested_end=requested_end,
        )
        text = json.dumps(rep, indent=2, ensure_ascii=False) + "\n"

        if write_stdout:
            sys.stdout.write(text)
        else:
            out = output_path or Path("cf_report_output.json")
            out.write_text(text, encoding="utf-8")
            if not opts.quiet:
                print(f"Wrote {out}", flush=True)

        if rate_fail:
            return exits.RATE_LIMIT_EXCEEDED
        return exits.SUCCESS


def run_clean(cfg: AppConfig, *, older_than: int | None, delete_all: bool, quiet: bool) -> int:
    cache_root = cfg.cache_path()
    try:
        with cache_lock(cache_root):
            if delete_all:
                for child in cache_root.iterdir():
                    if child.name == ".lock":
                        continue
                    if child.is_dir():
                        shutil.rmtree(child)
                    else:
                        child.unlink(missing_ok=True)
                if not quiet:
                    print(f"Cleared cache under {cache_root}", flush=True)
                return exits.SUCCESS
            if older_than is not None:
                cutoff = utc_today() - timedelta(days=older_than)
                removed = 0
                for zone_dir in cache_root.iterdir():
                    if not zone_dir.is_dir() or zone_dir.name.startswith("."):
                        continue
                    for day_dir in zone_dir.iterdir():
                        if not day_dir.is_dir():
                            continue
                        if day_dir.name.startswith("_"):
                            continue
                        try:
                            d = parse_ymd(day_dir.name)
                        except ValueError:
                            continue
                        if d < cutoff:
                            shutil.rmtree(day_dir)
                            removed += 1
                if not quiet:
                    print(
                        f"Removed {removed} day directories older than {older_than} days",
                        flush=True,
                    )
                return exits.SUCCESS
    except CacheLockTimeout as e:
        log.error("%s", e)
        return exits.CACHE_LOCK_TIMEOUT

    log.error("Specify --older-than N or --all")
    return exits.INVALID_PARAMS
