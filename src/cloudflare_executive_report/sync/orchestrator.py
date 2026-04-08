"""Sync cache and build JSON report."""

from __future__ import annotations

import json
import logging
import shutil
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from cloudflare_executive_report import exits
from cloudflare_executive_report.aggregate import (
    SECTION_BUILDERS,
    build_report,
    collect_days_payloads,
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
from cloudflare_executive_report.config import AppConfig
from cloudflare_executive_report.dates import (
    format_ymd,
    iter_dates_inclusive,
    last_n_complete_days,
    month_bounds,
    parse_ymd,
    utc_today,
    utc_yesterday,
    week_bounds,
    year_bounds,
)
from cloudflare_executive_report.executive.summary import build_executive_summary
from cloudflare_executive_report.fetchers.registry import (
    FETCHER_REGISTRY,
    day_cache_path,
    registered_stream_ids,
)
from cloudflare_executive_report.logging_config import effective_debug_enabled
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


def _streams_for_types(types: frozenset[str]) -> list[str]:
    return [sid for sid in registered_stream_ids() if sid in types]


def _semantic_current_bounds(opts: SyncOptions, *, y: date) -> tuple[date, date] | None:
    def _shift_year_keep_day(d: date, years: int) -> date:
        target_year = d.year + years
        day = d.day
        while day > 0:
            try:
                return date(target_year, d.month, day)
            except ValueError:
                day -= 1
        return date(target_year, d.month, 1)

    if opts.mode == SyncMode.yesterday:
        return y, y
    if opts.mode == SyncMode.last_week:
        this_week_start, _ = week_bounds(y)
        prev_week_end = this_week_start - timedelta(days=1)
        return week_bounds(prev_week_end)
    if opts.mode == SyncMode.this_week:
        start, _ = week_bounds(utc_today())
        return start, utc_today()
    if opts.mode == SyncMode.last_month:
        this_month_start, _ = month_bounds(y)
        prev_month_day = this_month_start - timedelta(days=1)
        return month_bounds(prev_month_day)
    if opts.mode == SyncMode.this_month:
        start, _ = month_bounds(utc_today())
        return start, utc_today()
    if opts.mode == SyncMode.last_year:
        t = utc_today()
        return date(t.year - 1, 1, 1), _shift_year_keep_day(t, -1)
    if opts.mode == SyncMode.this_year:
        start, _ = year_bounds(utc_today())
        return start, utc_today()
    return None


def _semantic_baseline_bounds(opts: SyncOptions, *, y: date) -> tuple[date, date] | None:
    if opts.mode == SyncMode.yesterday:
        d = y - timedelta(days=1)
        return d, d
    if opts.mode == SyncMode.last_week:
        this_week_start, _ = week_bounds(y)
        prev_week_end = this_week_start - timedelta(days=1)
        prev_week_start, _ = week_bounds(prev_week_end)
        return prev_week_start - timedelta(days=7), prev_week_start - timedelta(days=1)
    if opts.mode == SyncMode.this_week:
        this_week_start, _ = week_bounds(utc_today())
        prev_week_end = this_week_start - timedelta(days=1)
        return week_bounds(prev_week_end)
    if opts.mode == SyncMode.last_month:
        this_month_start, _ = month_bounds(y)
        prev_month_day = this_month_start - timedelta(days=1)
        prev_month_start, _ = month_bounds(prev_month_day)
        month_before_prev = prev_month_start - timedelta(days=1)
        return month_bounds(month_before_prev)
    if opts.mode == SyncMode.this_month:
        this_month_start, _ = month_bounds(utc_today())
        prev_month_day = this_month_start - timedelta(days=1)
        return month_bounds(prev_month_day)
    if opts.mode == SyncMode.last_year:
        return date(y.year - 2, 1, 1), date(y.year - 2, 12, 31)
    if opts.mode == SyncMode.this_year:
        current_start, _ = year_bounds(utc_today())
        return date(current_start.year - 1, 1, 1), date(current_start.year - 1, 12, 31)
    return None


def _sync_days_for_mode(opts: SyncOptions, idx, y: date) -> list[date]:
    semantic_bounds = _semantic_current_bounds(opts, y=y)
    if semantic_bounds is not None:
        d0, d1 = semantic_bounds
        return list(iter_dates_inclusive(d0, d1))
    if opts.mode == SyncMode.incremental:
        parts: list[date] = []
        for sid in _streams_for_types(opts.types):
            parts.extend(_dates_incremental(stream_latest(idx, sid), y))
        return sorted(set(parts))
    if opts.mode == SyncMode.last_n:
        assert opts.last_n is not None
        d0, d1 = last_n_complete_days(opts.last_n, yesterday=y)
        return list(iter_dates_inclusive(d0, d1))
    assert opts.start and opts.end
    d0, d1 = parse_ymd(opts.start), parse_ymd(opts.end)
    return list(iter_dates_inclusive(d0, d1))


def _rotate_report_outputs(cfg: AppConfig, *, history_date: date) -> None:
    current = cfg.report_current_path()
    if not current.is_file():
        return
    out_dir = cfg.report_outputs_dir()
    prev = cfg.report_previous_path()
    hist_dir = cfg.report_history_dir()
    ts = datetime.now(UTC).strftime("%Y-%m-%d_%H%M%S")
    hist_name = f"cf_report_{ts}.json"
    hist = hist_dir / hist_name
    out_dir.mkdir(parents=True, exist_ok=True)
    hist_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(current, prev)
    shutil.copy2(current, hist)


def _load_previous_report(cfg: AppConfig) -> dict | None:
    path = cfg.report_previous_path()
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _load_report_file(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _report_period(report: dict | None) -> tuple[date, date] | None:
    if not isinstance(report, dict):
        return None
    period = report.get("report_period")
    if not isinstance(period, dict):
        return None
    start = str(period.get("start") or "").strip()
    end = str(period.get("end") or "").strip()
    if not start or not end:
        return None
    try:
        return parse_ymd(start), parse_ymd(end)
    except ValueError:
        return None


def _find_previous_zone(previous_report: dict | None, zone_id: str) -> dict | None:
    if not isinstance(previous_report, dict):
        return None
    for zone in previous_report.get("zones") or []:
        if isinstance(zone, dict) and str(zone.get("zone_id") or "") == zone_id:
            return zone
    return None


def _report_has_zone(report: dict | None, zone_id: str) -> bool:
    return _find_previous_zone(report, zone_id) is not None


def _iter_baseline_candidates(cfg: AppConfig) -> list[dict]:
    out: list[dict] = []
    seen: set[Path] = set()
    p = cfg.report_previous_path()
    if p.is_file():
        seen.add(p.resolve())
        rep = _load_report_file(p)
        if rep is not None:
            out.append(rep)
    hist = cfg.report_history_dir()
    if hist.is_dir():
        for f in sorted(hist.glob("cf_report_*.json"), reverse=True):
            rf = f.resolve()
            if rf in seen:
                continue
            seen.add(rf)
            rep = _load_report_file(f)
            if rep is not None:
                out.append(rep)
    return out


def select_previous_report_for_period(
    cfg: AppConfig,
    *,
    current_start: str,
    current_end: str,
    zone_id: str,
    opts: SyncOptions,
    y: date | None = None,
) -> dict | None:
    try:
        cs = parse_ymd(current_start)
        ce = parse_ymd(current_end)
    except ValueError:
        return None
    baseline_expected = _semantic_baseline_bounds(opts, y=y or utc_yesterday())
    current_len = (ce - cs).days + 1
    best: tuple[date, dict] | None = None
    for rep in _iter_baseline_candidates(cfg):
        period = _report_period(rep)
        if period is None:
            continue
        ps, pe = period
        if pe >= cs:
            continue
        if ps == cs and pe == ce:
            continue
        if not _report_has_zone(rep, zone_id):
            continue
        if baseline_expected is not None:
            if (ps, pe) != baseline_expected:
                continue
        else:
            if ((pe - ps).days + 1) != current_len:
                continue
        if best is None or pe > best[0]:
            best = (pe, rep)
    return best[1] if best is not None else None


def _report_bounds_from_indices(
    zones: list,
    cache_root: Path,
    y: date,
    opts: SyncOptions,
) -> tuple[str, str]:
    semantic_bounds = _semantic_current_bounds(opts, y=y)
    if semantic_bounds is not None:
        d0, d1 = semantic_bounds
        return format_ymd(d0), format_ymd(d1)
    if opts.mode == SyncMode.last_n and opts.last_n is not None:
        d0, d1 = last_n_complete_days(opts.last_n, yesterday=y)
        return format_ymd(d0), format_ymd(d1)
    if opts.mode == SyncMode.range and opts.start and opts.end:
        return opts.start, opts.end

    earliests: list[str] = []
    latests: list[str] = []
    for z in zones:
        ix = load_zone_index(cache_root, z.id, z.name)
        for sid in _streams_for_types(opts.types):
            st = ix.streams.get(sid)
            if not st:
                continue
            if st.earliest:
                earliests.append(st.earliest)
            if st.latest:
                latests.append(st.latest)
    if not earliests:
        earliests.append(format_ymd(y))
    if not latests:
        latests.append(format_ymd(y))
    return min(earliests), max(latests)


def pdf_report_period_for_options(
    cfg: AppConfig,
    opts: SyncOptions,
    *,
    zone_filter: str | None = None,
) -> tuple[str, str]:
    """Return ``(report_start, report_end)`` for the PDF span (same logic as JSON ``run_sync``)."""
    cache_root = cfg.cache_path()
    zones = list(cfg.zones)
    if zone_filter:
        zf = zone_filter.strip()
        zones = [z for z in zones if z.id == zf or z.name == zf]
        if not zones:
            msg = f"Zone not found in config: {zone_filter!r}"
            raise ValueError(msg)
    if not zones:
        msg = "No zones configured. Use `cf-report zones add` or set `zones` in config."
        raise ValueError(msg)
    y = utc_yesterday()
    report_start, report_end = _report_bounds_from_indices(zones, cache_root, y, opts)
    if opts.include_today:
        report_end = format_ymd(utc_today())
    return report_start, report_end


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
    verbose_http = effective_debug_enabled()
    streams = _streams_for_types(opts.types)
    default_output_mode = (not write_stdout) and (output_path is None)
    if default_output_mode:
        _rotate_report_outputs(cfg, history_date=utc_today())

    with CloudflareClient(cfg.api_token, verbose=verbose_http) as client:
        if opts.mode == SyncMode.range and opts.start and opts.end:
            if parse_ymd(opts.end) > y:
                log.error("--end cannot be after yesterday (UTC). Use --include-today for today.")
                return exits.INVALID_PARAMS

        # Cache zone metadata once per run to avoid redundant API calls
        zmeta_by_zone_id: dict[str, dict] = {}
        for z in zones:
            try:
                zmeta_by_zone_id[z.id] = get_zone(client, z.id)
            except CloudflareAuthError as e:
                log.error("%s", e)
                return exits.AUTH_FAILED
            except CloudflareAPIError as e:
                log.error("Zone lookup failed: %s", e)
                return exits.GENERAL_ERROR

        for z in zones:
            _progress(f"Zone {z.name} ({z.id})", quiet=opts.quiet)
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

        report_start, report_end = _report_bounds_from_indices(zones, cache_root, y, opts)
        requested_start, requested_end = report_start, report_end
        if opts.include_today:
            report_end = format_ymd(utc_today())
            requested_end = report_end

        zones_out: list[dict] = []
        all_warnings: list[str] = []

        for z in zones:
            zmeta = zmeta_by_zone_id[z.id]
            plan = (zmeta.get("plan") or {}).get("legacy_id")

            cache_end = format_ymd(y) if opts.include_today else report_end
            zblock: dict = {"zone_id": z.id, "zone_name": z.name}
            zone_warnings: list[str] = []

            for sid in _streams_for_types(opts.types):
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

            zh, zw = fetch_zone_health(
                client,
                z.id,
                z.name,
                skip=opts.skip_zone_health,
                zone_meta=zmeta,
            )
            zblock["zone_health"] = zh
            all_warnings.extend(zw)
            zone_warnings.extend(zw)
            previous_report = select_previous_report_for_period(
                cfg,
                current_start=report_start,
                current_end=report_end,
                zone_id=z.id,
                opts=opts,
                y=y,
            )
            zblock["executive_summary"] = build_executive_summary(
                zone_id=z.id,
                zone_name=z.name,
                zone_health=zh,
                dns=zblock.get("dns"),
                http=zblock.get("http"),
                security=zblock.get("security"),
                cache=zblock.get("cache"),
                http_adaptive=zblock.get("http_adaptive"),
                dns_records=zblock.get("dns_records"),
                audit=zblock.get("audit"),
                certificates=zblock.get("certificates"),
                warnings=zone_warnings,
                as_of_date=parse_ymd(report_end),
                current_period={"start": report_start, "end": report_end},
                previous_report=previous_report,
                previous_zone=_find_previous_zone(previous_report, z.id),
            )

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
            out = output_path or cfg.report_current_path()
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(text, encoding="utf-8")
            if not opts.quiet:
                print(f"Wrote {out}", flush=True)

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
    cache_root = cfg.cache_path()
    history_root = cfg.report_history_dir()
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

            if older_than is not None:
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
                            ds = ds.split("_", 1)[0]
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

    log.error("Specify cleanup scope: --cache, --history, or --all")
    return exits.INVALID_PARAMS
