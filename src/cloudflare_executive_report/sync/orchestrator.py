"""Sync cache and build JSON report."""

from __future__ import annotations

import json
import logging
import shutil
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from cloudflare_executive_report import exits
from cloudflare_executive_report.aggregate import (
    build_report,
    collect_days_payloads,
)
from cloudflare_executive_report.aggregators import (
    SECTION_BUILDERS,
)
from cloudflare_executive_report.cache import (
    CacheLockTimeout,
    cache_lock,
    load_zone_index,
    merge_stream_bounds,
    read_day_file,
    save_zone_index,
    stream_latest,
)
from cloudflare_executive_report.cf_client import (
    CloudflareAPIError,
    CloudflareAuthError,
    CloudflareClient,
)
from cloudflare_executive_report.common.dates import (
    format_ymd,
    iter_dates_inclusive,
    last_n_complete_days,
    parse_ymd,
    utc_today,
    utc_yesterday,
)
from cloudflare_executive_report.common.formatting import progress_message
from cloudflare_executive_report.common.logging_config import effective_debug_enabled
from cloudflare_executive_report.common.period_resolver import (
    build_data_fingerprint,
    report_type_for_options,
    resolved_period_for_options,
)
from cloudflare_executive_report.common.report_cache import missing_stream_days_for_zone
from cloudflare_executive_report.common.report_period import (
    report_bounds_from_indices,
    streams_for_sync_types,
)
from cloudflare_executive_report.config import AppConfig
from cloudflare_executive_report.fetchers.registry import (
    FETCHER_REGISTRY,
    day_cache_path,
)
from cloudflare_executive_report.report.zone_block import (
    update_zone_json_block_health_and_executive,
)
from cloudflare_executive_report.sync.day_processor import process_day
from cloudflare_executive_report.sync.options import SyncMode, SyncOptions

log = logging.getLogger(__name__)


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


def _sync_days_for_mode(opts: SyncOptions, idx, y: date) -> list[date]:
    resolved = resolved_period_for_options(opts=opts, y=y, today=utc_today())
    if resolved is not None:
        d0, d1 = resolved
        return list(iter_dates_inclusive(d0, d1))
    if opts.mode == SyncMode.incremental:
        parts: list[date] = []
        for sid in streams_for_sync_types(opts.types):
            parts.extend(_dates_incremental(stream_latest(idx, sid), y))
        return sorted(set(parts))
    if opts.mode == SyncMode.last_n:
        assert opts.last_n is not None
        d0, d1 = last_n_complete_days(opts.last_n, yesterday=y)
        return list(iter_dates_inclusive(d0, d1))
    assert opts.start and opts.end
    d0, d1 = parse_ymd(opts.start), parse_ymd(opts.end)
    return list(iter_dates_inclusive(d0, d1))


def _rotate_report_outputs(cfg: AppConfig) -> None:
    current = cfg.report_current_path()
    if not current.is_file():
        return

    try:
        with open(current, encoding="utf-8") as f:
            data = json.load(f)
            fp = data.get("data_fingerprint")
            if fp:
                from cloudflare_executive_report.common.period_resolver import (
                    compute_fingerprint_hash,
                )

                fp_hash = compute_fingerprint_hash(fp)
            else:
                log.error("Current report missing data_fingerprint; skipping rotation.")
                return
    except Exception as e:
        log.error("Failed to read current report for rotation: %s", e)
        return

    hist_dir = cfg.history_path()
    ts = datetime.now(UTC).strftime("%Y-%m-%d_%H%M%S")
    hist_name = f"cf_report_{fp_hash}_{ts}.json"
    hist = hist_dir / hist_name
    hist_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(current, hist)


def _normalize_report_for_comparison(data: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of the report data without volatile timestamps for comparison."""
    return {k: v for k, v in data.items() if k not in ("generated_at", "zone_health_fetched_at")}


def run_sync(
    cfg: AppConfig,
    opts: SyncOptions,
    *,
    zone_filter: str | None = None,
    output_path: Path | None = None,
    write_stdout: bool = False,
    write_report_json: bool = True,
) -> int:
    """
    Synchronize the local cache with Cloudflare API data and optionally generate a JSON report.

    Returns an exit code (0 for success).
    """
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
                write_report_json=write_report_json,
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
    write_report_json: bool,
) -> int:
    rate_fail = False
    verbose_http = effective_debug_enabled()
    streams = streams_for_sync_types(opts.types)
    default_output_mode = (not write_stdout) and (output_path is None)

    with CloudflareClient(cfg.api_token, verbose=verbose_http) as client:
        if opts.mode == SyncMode.range and opts.start and opts.end:
            if parse_ymd(opts.end) > y:
                log.error("--end cannot be after yesterday (UTC). Use --include-today for today.")
                return exits.INVALID_PARAMS

        # Cache zone metadata once per run to avoid redundant API calls
        zmeta_by_zone_id: dict[str, dict] = {}
        for z in zones:
            try:
                zmeta_by_zone_id[z.id] = client.get_zone(z.id)
            except CloudflareAuthError as e:
                log.error("%s", e)
                return exits.AUTH_FAILED
            except CloudflareAPIError as e:
                log.error("Zone lookup failed: %s", e)
                return exits.GENERAL_ERROR

        for z in zones:
            progress_message(f"Zone {z.name} ({z.id})", quiet=opts.quiet)
            zmeta = zmeta_by_zone_id[z.id]

            plan = (zmeta.get("plan") or {}).get("legacy_id")

            idx = load_zone_index(cache_root, z.id, z.name)
            idx.zone_name = z.name

            # Only --refresh forces re-download; --last / --start/--end define the day set.
            force_fetch = opts.refresh
            days = _sync_days_for_mode(opts, idx, y)

            for d in days:
                for sid in streams:
                    fetcher = FETCHER_REGISTRY[sid]
                    if process_day(
                        fetcher,
                        client,
                        cache_root,
                        z.id,
                        z.name,
                        d,
                        plan_legacy_id=plan,
                        zone_meta=zmeta,
                        force_fetch=force_fetch,
                        refresh=opts.refresh,
                        quiet=opts.quiet,
                    ):
                        rate_fail = True

            new_idx = load_zone_index(cache_root, z.id, z.name)
            new_idx.zone_name = z.name
            if days:
                s, e = format_ymd(min(days)), format_ymd(max(days))
                for sid in streams:
                    new_idx = merge_stream_bounds(new_idx, s, e, sid)
                if opts.mode == SyncMode.incremental:
                    yy = format_ymd(y)
                    for sid in streams:
                        new_idx = merge_stream_bounds(new_idx, None, yy, sid)
            save_zone_index(cache_root, new_idx)

        if not write_report_json:
            if rate_fail:
                return exits.RATE_LIMIT_EXCEEDED
            return exits.SUCCESS

        report_start, report_end = report_bounds_from_indices(zones, cache_root, y, opts)
        requested_start, requested_end = report_start, report_end
        if opts.include_today:
            report_end = format_ymd(utc_today())
            requested_end = report_end

        cache_end_for_missing = format_ymd(y) if opts.include_today else report_end
        stream_ids_merge = streams_for_sync_types(opts.types)
        all_missing_days: set[str] = set()
        for z in zones:
            all_missing_days |= missing_stream_days_for_zone(
                cache_root, z.id, report_start, cache_end_for_missing, stream_ids_merge
            )
        missing_days_sorted = sorted(all_missing_days)
        partial = len(missing_days_sorted) > 0

        zones_out: list[dict] = []
        all_warnings: list[str] = []

        for z in zones:
            zmeta = zmeta_by_zone_id[z.id]
            plan = (zmeta.get("plan") or {}).get("legacy_id")

            cache_end = format_ymd(y) if opts.include_today else report_end
            zblock: dict = {"zone_id": z.id, "zone_name": z.name}
            zone_warnings: list[str] = []

            for sid in streams_for_sync_types(opts.types):
                fetcher = FETCHER_REGISTRY[sid]
                builder = SECTION_BUILDERS[sid]

                def read_stream(zi: str, ds: str, stream_id: str = sid) -> dict | None:
                    return read_day_file(day_cache_path(cache_root, zi, ds, stream_id))

                api_days, warns = collect_days_payloads(
                    read_stream,
                    z.id,
                    z.name,
                    report_start,
                    cache_end,
                    label=fetcher.collect_label,
                )
                if opts.include_today:
                    extra, tw, rl = fetcher.append_live_today(
                        client, z.id, z.name, plan_legacy_id=plan, zone_meta=zmeta
                    )
                    api_days = api_days + extra
                    warns.extend(tw)
                    if rl:
                        rate_fail = True
                zblock[sid] = builder(api_days, top=opts.top)
                all_warnings.extend(warns)
                zone_warnings.extend(warns)

            zw = update_zone_json_block_health_and_executive(
                cfg=cfg,
                opts=opts,
                client=client,
                zone_id=z.id,
                zone_name=z.name,
                zone_meta=zmeta,
                zone_block=zblock,
                report_start=report_start,
                report_end=report_end,
                y=y,
                summary_warnings=zone_warnings,
            )
            all_warnings.extend(zw)

            zones_out.append(zblock)

        rep = build_report(
            zones_out=zones_out,
            warnings=all_warnings,
            period_start=report_start,
            period_end=report_end,
            requested_start=requested_start,
            requested_end=requested_end,
            report_type=report_type_for_options(opts),
            data_fingerprint=build_data_fingerprint(
                start=report_start,
                end=report_end,
                top=opts.top,
                types=opts.types,
                include_today=opts.include_today,
            ),
            zone_health_fetched_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            partial=partial,
            missing_days=missing_days_sorted,
        )
        text = json.dumps(rep, indent=2, ensure_ascii=False) + "\n"

        if write_stdout:
            sys.stdout.write(text)
        else:
            out = output_path or cfg.report_current_path()

            if default_output_mode:
                # Only rotate if data changed compared to existing file
                from cloudflare_executive_report.report.snapshot import load_report_json

                existing = load_report_json(out)
                if existing:
                    if _normalize_report_for_comparison(
                        existing
                    ) != _normalize_report_for_comparison(rep):
                        _rotate_report_outputs(cfg)
                elif out.is_file():
                    # If it's a file but not a valid report JSON, rotate it anyway
                    _rotate_report_outputs(cfg)

            from cloudflare_executive_report.report.snapshot import save_report_json

            save_report_json(out, rep, quiet=opts.quiet)

        if rate_fail:
            return exits.RATE_LIMIT_EXCEEDED
        return exits.SUCCESS


def run_clean(
    cfg: AppConfig,
    *,
    older_than: int | None,
    scope_cache: bool,
    scope_history: bool,
    quiet: bool,
) -> int:
    """Remove cached data and/or report history files."""
    if not scope_cache and not scope_history:
        log.error("Specify cleanup scope: --cache, --history, or --all")
        return exits.INVALID_PARAMS

    cache_root = cfg.cache_path()
    history_root = cfg.history_path()
    try:
        with cache_lock(cache_root):
            if older_than is None:
                if scope_cache:
                    for child in cache_root.iterdir():
                        if child.name == ".lock":
                            continue
                        if child.is_dir():
                            shutil.rmtree(child)
                        else:
                            child.unlink(missing_ok=True)
                    if not quiet:
                        print(f"Cleared cache under {cache_root}", flush=True)
                if scope_history and history_root.exists():
                    shutil.rmtree(history_root)
                    if not quiet:
                        print(f"Cleared history under {history_root}", flush=True)
                return exits.SUCCESS

            assert older_than is not None
            cutoff = utc_today() - timedelta(days=older_than)
            removed_cache = 0
            removed_history = 0
            if scope_cache:
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
                            removed_cache += 1
            if scope_history and history_root.exists():
                for report_file in history_root.glob("cf_report_*.json"):
                    stem = report_file.stem
                    ds = stem.replace("cf_report_", "", 1)
                    if "_" in ds:
                        parts = ds.split("_")
                        # If first part is exactly 16 chars (our hash), date is the second part
                        if len(parts) >= 2 and len(parts[0]) == 16:
                            ds = parts[1]
                        else:
                            ds = parts[0]
                    try:
                        d = parse_ymd(ds)
                    except ValueError:
                        continue
                    if d < cutoff:
                        report_file.unlink(missing_ok=True)
                        removed_history += 1
            if not quiet:
                if scope_cache:
                    print(
                        "Removed "
                        f"{removed_cache} cache day directories "
                        f"older than {older_than} days",
                        flush=True,
                    )
                if scope_history:
                    print(
                        "Removed "
                        f"{removed_history} history report files "
                        f"older than {older_than} days",
                        flush=True,
                    )
            return exits.SUCCESS
    except CacheLockTimeout as e:
        log.error("%s", e)
        return exits.CACHE_LOCK_TIMEOUT
