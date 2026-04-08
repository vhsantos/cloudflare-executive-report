"""Shared CLI helpers for sync and report (single source for date rules and SyncOptions)."""

from __future__ import annotations

from pathlib import Path

from cloudflare_executive_report.config import AppConfig, ZoneEntry, load_config
from cloudflare_executive_report.dates import parse_ymd
from cloudflare_executive_report.sync.options import SyncMode, SyncOptions


class CliValidationError(ValueError):
    """Invalid flags or values; map to INVALID_PARAMS."""


class CliConfigError(Exception):
    """Config load failure; map to GENERAL_ERROR."""


def load_app_config(config_path: Path | None) -> AppConfig:
    try:
        return load_config(config_path)
    except (FileNotFoundError, ValueError) as e:
        raise CliConfigError(str(e)) from e


def resolve_zone_filter(cfg: AppConfig, zone_option: str | None) -> str | None:
    """Same as sync/report: explicit --zone, else default_zone, else all zones (None filter)."""
    raw = (zone_option.strip() if zone_option else "") or (cfg.default_zone or "").strip()
    return raw or None


def zone_ids_for_report(cfg: AppConfig, zone_filter: str | None) -> list[str]:
    """Zone id list for PDF/ReportSpec (one id or all configured)."""
    if zone_filter:
        return [zone_filter.strip()]
    return [z.id for z in cfg.zones]


def zones_matching_filter(cfg: AppConfig, zone_filter: str | None) -> list[ZoneEntry]:
    """Zones included for this filter (same resolution as ``run_sync``)."""
    zones = list(cfg.zones)
    if zone_filter:
        zf = zone_filter.strip()
        zones = [z for z in zones if z.id == zf or z.name == zf]
    return zones


def cache_has_any_zone_data(cache_root: Path, zones: list[ZoneEntry]) -> bool:
    """True if at least one zone has a non-empty cache directory under ``cache_root``."""
    for z in zones:
        zdir = cache_root / z.id
        if not zdir.is_dir():
            continue
        try:
            if any(zdir.iterdir()):
                return True
        except OSError:
            continue
    return False


# Cap for ranked lists (large values hurt API payloads and PDF layout).
CLI_TOP_MAX = 100


def validate_and_build_sync_options(
    *,
    end: str | None,
    include_today: bool,
    last_month: bool,
    last_week: bool,
    last_year: bool,
    last: int | None,
    quiet: bool,
    refresh: bool,
    skip_zone_health: bool,
    start: str | None,
    this_month: bool,
    this_week: bool,
    this_year: bool,
    top: int,
    type_set: frozenset[str],
    yesterday: bool,
) -> SyncOptions:
    """Validate shared date flags and build ``SyncOptions`` (used by ``sync`` and ``report``)."""
    if top < 1:
        raise CliValidationError("Error: --top must be at least 1.")
    if top > CLI_TOP_MAX:
        raise CliValidationError(
            f"Error: --top cannot exceed {CLI_TOP_MAX} (performance / layout limit)."
        )
    if (start is None) != (end is None):
        raise CliValidationError("Error: --start and --end must be used together.")
    if last is not None and (start is not None or end is not None):
        raise CliValidationError("Error: use either --last N or --start/--end, not both.")
    semantic_modes = {
        SyncMode.last_month: last_month,
        SyncMode.last_week: last_week,
        SyncMode.last_year: last_year,
        SyncMode.this_month: this_month,
        SyncMode.this_week: this_week,
        SyncMode.this_year: this_year,
        SyncMode.yesterday: yesterday,
    }
    selected_semantic = [mode for mode, enabled in semantic_modes.items() if enabled]
    if len(selected_semantic) > 1:
        raise CliValidationError("Error: choose only one semantic period flag at a time.")
    if selected_semantic and (last is not None or start is not None or end is not None):
        raise CliValidationError(
            "Error: semantic period flags cannot be combined with --last or --start/--end."
        )
    if last is not None and last < 1:
        raise CliValidationError("Error: --last must be at least 1.")
    if start and end:
        try:
            parse_ymd(start)
            parse_ymd(end)
        except ValueError as e:
            raise CliValidationError("Invalid --start/--end (use YYYY-MM-DD).") from e

    if selected_semantic:
        return SyncOptions(
            mode=selected_semantic[0],
            refresh=refresh,
            include_today=include_today,
            quiet=quiet,
            types=type_set,
            top=top,
            skip_zone_health=skip_zone_health,
        )
    if last is not None:
        return SyncOptions(
            mode=SyncMode.last_n,
            last_n=last,
            refresh=refresh,
            include_today=include_today,
            quiet=quiet,
            types=type_set,
            top=top,
            skip_zone_health=skip_zone_health,
        )
    if start and end:
        return SyncOptions(
            mode=SyncMode.range,
            start=start,
            end=end,
            refresh=refresh,
            include_today=include_today,
            quiet=quiet,
            types=type_set,
            top=top,
            skip_zone_health=skip_zone_health,
        )
    return SyncOptions(
        mode=SyncMode.incremental,
        refresh=refresh,
        include_today=include_today,
        quiet=quiet,
        types=type_set,
        top=top,
        skip_zone_health=skip_zone_health,
    )
