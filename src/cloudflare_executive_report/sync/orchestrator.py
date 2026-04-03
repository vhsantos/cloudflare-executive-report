"""Sync cache and build JSON report."""

from __future__ import annotations

import json
import logging
import shutil
import sys
from datetime import date, timedelta
from pathlib import Path

from cloudflare_executive_report import exits
from cloudflare_executive_report.aggregate import (
    build_dns_section,
    build_http_section,
    build_report,
    build_security_section,
    collect_days_payloads,
)
from cloudflare_executive_report.cache import (
    CacheLockTimeout,
    CacheStream,
    cache_lock,
    day_path,
    load_zone_index,
    merge_stream_bounds,
    read_day_file,
    save_zone_index,
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
from cloudflare_executive_report.fetchers import (
    fetch_dns_for_bounds,
    fetch_http_for_date,
    fetch_security_partial_utc_day,
)
from cloudflare_executive_report.fetchers.registry import FETCHER_REGISTRY
from cloudflare_executive_report.retention import (
    date_outside_dns_retention,
    date_outside_http_retention,
    date_outside_security_retention,
    dns_retention_days,
    security_retention_days,
)
from cloudflare_executive_report.sync.day_processor import process_day
from cloudflare_executive_report.sync.options import SyncMode, SyncOptions
from cloudflare_executive_report.zone_health import fetch_zone_health
from cloudflare_executive_report.zones_api import get_zone

log = logging.getLogger(__name__)


def _progress(msg: str, *, quiet: bool) -> None:
    if not quiet:
        print(msg, flush=True)


def _dates_incremental(idx_latest: str | None, y: date) -> list[date]:
    if idx_latest:
        latest = parse_ymd(idx_latest)
    else:
        latest = y
    out: list[date] = []
    d = latest + timedelta(days=1)
    while d <= y:
        out.append(d)
        d += timedelta(days=1)
    return out


def _streams_for_types(types: frozenset[str]) -> list[CacheStream]:
    order = (CacheStream.dns, CacheStream.http, CacheStream.security)
    return [s for s in order if s.value in types]


def _sync_days_for_mode(opts: SyncOptions, idx, y: date) -> list[date]:
    if opts.mode == SyncMode.incremental:
        parts: list[date] = []
        if "dns" in opts.types:
            parts.extend(_dates_incremental(idx.dns.latest, y))
        if "http" in opts.types:
            parts.extend(_dates_incremental(idx.http.latest, y))
        if "security" in opts.types:
            parts.extend(_dates_incremental(idx.security.latest, y))
        return sorted(set(parts))
    if opts.mode == SyncMode.last_n:
        assert opts.last_n is not None
        d0, d1 = last_n_complete_days(opts.last_n, yesterday=y)
        return list(iter_dates_inclusive(d0, d1))
    assert opts.start and opts.end
    d0, d1 = parse_ymd(opts.start), parse_ymd(opts.end)
    return list(iter_dates_inclusive(d0, d1))


def _report_bounds_from_indices(
    zones: list,
    cache_root: Path,
    y: date,
    opts: SyncOptions,
) -> tuple[str, str]:
    if opts.mode == SyncMode.last_n and opts.last_n is not None:
        d0, d1 = last_n_complete_days(opts.last_n, yesterday=y)
        return format_ymd(d0), format_ymd(d1)
    if opts.mode == SyncMode.range and opts.start and opts.end:
        return opts.start, opts.end

    earliests: list[str] = []
    latests: list[str] = []
    for z in zones:
        ix = load_zone_index(cache_root, z.id, z.name)
        if "dns" in opts.types:
            if ix.dns.earliest:
                earliests.append(ix.dns.earliest)
            if ix.dns.latest:
                latests.append(ix.dns.latest)
        if "http" in opts.types:
            if ix.http.earliest:
                earliests.append(ix.http.earliest)
            if ix.http.latest:
                latests.append(ix.http.latest)
        if "security" in opts.types:
            if ix.security.earliest:
                earliests.append(ix.security.earliest)
            if ix.security.latest:
                latests.append(ix.security.latest)
    if not earliests:
        earliests.append(format_ymd(y))
    if not latests:
        latests.append(format_ymd(y))
    return min(earliests), max(latests)


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
    y: date,
    *,
    output_path: Path | None,
    write_stdout: bool,
) -> int:
    rate_fail = False
    verbose_http = log.isEnabledFor(logging.DEBUG)
    streams = _streams_for_types(opts.types)

    with CloudflareClient(cfg.api_token, verbose=verbose_http) as client:
        if opts.mode == SyncMode.range and opts.start and opts.end:
            if parse_ymd(opts.end) > y:
                log.error("--end cannot be after yesterday (UTC). Use --include-today for today.")
                return exits.INVALID_PARAMS

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

            idx = load_zone_index(cache_root, z.id, z.name)
            idx.zone_name = z.name

            force_fetch = opts.mode in (SyncMode.last_n, SyncMode.range)
            days = _sync_days_for_mode(opts, idx, y)

            for d in days:
                for stream in streams:
                    fetcher = FETCHER_REGISTRY[stream]
                    if process_day(
                        fetcher,
                        client,
                        cache_root,
                        z.id,
                        z.name,
                        d,
                        plan_legacy_id=plan,
                        force_fetch=force_fetch,
                        refresh=opts.refresh,
                        quiet=opts.quiet,
                    ):
                        rate_fail = True

            new_idx = load_zone_index(cache_root, z.id, z.name)
            new_idx.zone_name = z.name
            if days:
                s, e = format_ymd(min(days)), format_ymd(max(days))
                for stream in streams:
                    new_idx = merge_stream_bounds(new_idx, s, e, stream)
                if opts.mode == SyncMode.incremental:
                    yy = format_ymd(y)
                    for stream in streams:
                        new_idx = merge_stream_bounds(new_idx, None, yy, stream)
            save_zone_index(cache_root, new_idx)

        report_start, report_end = _report_bounds_from_indices(zones, cache_root, y, opts)
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
            dns_ret = dns_retention_days(plan)
            sec_ret = security_retention_days(plan)

            cache_end = format_ymd(y) if opts.include_today else report_end
            zblock: dict = {"zone_id": z.id, "zone_name": z.name}

            if "dns" in opts.types:

                def read_d(zi: str, ds: str) -> dict | None:
                    return read_day_file(day_path(cache_root, zi, ds, CacheStream.dns))

                api_days, warns = collect_days_payloads(
                    read_d, z.id, z.name, report_start, cache_end, label="DNS"
                )
                if opts.include_today:
                    t = utc_today()
                    if not date_outside_dns_retention(t, dns_ret):
                        ge, lt = day_bounds_utc(t)
                        try:
                            td = fetch_dns_for_bounds(client, z.id, ge, lt)
                            api_days = api_days + [td]
                            warns.append(
                                "Report includes today's UTC date; "
                                "DNS data may be incomplete until the day finishes."
                            )
                        except CloudflareRateLimitError:
                            rate_fail = True
                            warns.append(
                                "Could not fetch today's DNS data for zone "
                                f"{z.name} (rate limited)."
                            )
                        except CloudflareAPIError as e:
                            warns.append(f"Could not fetch today's DNS data for zone {z.name}: {e}")
                zblock["dns"] = build_dns_section(api_days, top=opts.top)
                all_warnings.extend(warns)

            if "http" in opts.types:

                def read_h(zi: str, ds: str) -> dict | None:
                    return read_day_file(day_path(cache_root, zi, ds, CacheStream.http))

                h_days, hw = collect_days_payloads(
                    read_h, z.id, z.name, report_start, cache_end, label="HTTP"
                )
                if opts.include_today:
                    t = utc_today()
                    if not date_outside_http_retention(t):
                        try:
                            ht = fetch_http_for_date(client, z.id, format_ymd(t))
                            h_days = h_days + [ht]
                            hw.append(
                                "Report includes today's UTC date; "
                                "HTTP data may be incomplete until the day finishes."
                            )
                        except CloudflareRateLimitError:
                            rate_fail = True
                            hw.append(
                                "Could not fetch today's HTTP data for zone "
                                f"{z.name} (rate limited)."
                            )
                        except CloudflareAPIError as e:
                            hw.append(f"Could not fetch today's HTTP data for zone {z.name}: {e}")
                zblock["http"] = build_http_section(h_days, top=opts.top)
                all_warnings.extend(hw)

            if "security" in opts.types:

                def read_s(zi: str, ds: str) -> dict | None:
                    return read_day_file(day_path(cache_root, zi, ds, CacheStream.security))

                s_days, sw = collect_days_payloads(
                    read_s, z.id, z.name, report_start, cache_end, label="Security"
                )
                if opts.include_today:
                    t = utc_today()
                    if not date_outside_security_retention(t, sec_ret):
                        try:
                            st = fetch_security_partial_utc_day(client, z.id, t)
                            s_days = s_days + [st]
                            sw.append(
                                "Report includes today's UTC date; "
                                "security events may be incomplete until the day finishes."
                            )
                        except CloudflareRateLimitError:
                            rate_fail = True
                            sw.append(
                                f"Could not fetch today's security data for zone {z.name} "
                                "(rate limited)."
                            )
                        except CloudflareAPIError as e:
                            sw.append(
                                f"Could not fetch today's security data for zone {z.name}: {e}"
                            )
                zblock["security"] = build_security_section(s_days)
                all_warnings.extend(sw)

            zh, zw = fetch_zone_health(client, z.id, z.name, skip=opts.no_config)
            zblock["zone_health"] = zh
            all_warnings.extend(zw)

            zones_out.append(zblock)

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
