"""Resolve PDF/report JSON date span from config, cache indices, and sync options."""

from __future__ import annotations

from cloudflare_executive_report.common.dates import format_ymd, utc_today, utc_yesterday
from cloudflare_executive_report.common.report_period import report_bounds_from_indices
from cloudflare_executive_report.config import AppConfig
from cloudflare_executive_report.sync.options import SyncOptions


def pdf_report_period_for_options(
    cfg: AppConfig,
    opts: SyncOptions,
    *,
    zone_filter: str | None = None,
) -> tuple[str, str]:
    """Return inclusive UTC start/end date strings for the report span."""
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
    report_start, report_end = report_bounds_from_indices(zones, cache_root, y, opts)
    if opts.include_today:
        report_end = format_ymd(utc_today())
    return report_start, report_end
