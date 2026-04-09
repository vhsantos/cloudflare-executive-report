"""Refresh zone health in an existing report JSON without syncing analytics streams."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from cloudflare_executive_report import exits
from cloudflare_executive_report.cf_client import (
    CloudflareAPIError,
    CloudflareAuthError,
    CloudflareClient,
)
from cloudflare_executive_report.common.dates import utc_yesterday
from cloudflare_executive_report.common.logging_config import effective_debug_enabled
from cloudflare_executive_report.common.report_snapshot import is_report_snapshot_valid
from cloudflare_executive_report.config import AppConfig
from cloudflare_executive_report.report.snapshot import load_report_json, save_report_json
from cloudflare_executive_report.report.zone_block import (
    update_zone_json_block_health_and_executive,
)
from cloudflare_executive_report.sync.options import SyncOptions

log = logging.getLogger(__name__)


def refresh_report_json_zone_health_only(
    cfg: AppConfig,
    opts: SyncOptions,
    *,
    zone_filter: str | None = None,
) -> int:
    """Fetch zone health, rebuild executive summaries, and rewrite current report JSON."""
    out = cfg.report_current_path()
    report_raw = load_report_json(out)
    if report_raw is None or not is_report_snapshot_valid(report_raw):
        log.error("Current report JSON missing or invalid for health-only refresh.")
        return exits.INVALID_PARAMS

    zones = list(cfg.zones)
    if zone_filter:
        zf = zone_filter.strip()
        zones = [z for z in zones if z.id == zf or z.name == zf]
        if not zones:
            log.error("Zone not found: %s", zone_filter)
            return exits.INVALID_PARAMS

    period = report_raw.get("report_period")
    if not isinstance(period, dict):
        return exits.INVALID_PARAMS
    start = str(period.get("start") or "").strip()
    end = str(period.get("end") or "").strip()
    if not start or not end:
        return exits.INVALID_PARAMS

    zones_payload = report_raw.get("zones") or []
    if not isinstance(zones_payload, list):
        return exits.INVALID_PARAMS
    zblocks_by_id: dict[str, dict] = {}
    for item in zones_payload:
        if isinstance(item, dict):
            zid = str(item.get("zone_id") or "").strip()
            if zid:
                zblocks_by_id[zid] = item

    for z in zones:
        if z.id not in zblocks_by_id:
            log.error("Report JSON missing zone block for %s (%s)", z.id, z.name)
            return exits.GENERAL_ERROR

    y = utc_yesterday()
    verbose_http = effective_debug_enabled()
    merged_warnings: list[str] = []
    raw_warns = report_raw.get("warnings")
    if isinstance(raw_warns, list):
        merged_warnings.extend(str(w) for w in raw_warns)

    try:
        with CloudflareClient(cfg.api_token, verbose=verbose_http) as client:
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
                zb = zblocks_by_id[z.id]
                zmeta = zmeta_by_zone_id[z.id]
                summary_warnings: list[str] = []
                zw = update_zone_json_block_health_and_executive(
                    cfg=cfg,
                    opts=opts,
                    client=client,
                    zone_id=z.id,
                    zone_name=z.name,
                    zone_meta=zmeta,
                    zone_block=zb,
                    report_start=start,
                    report_end=end,
                    y=y,
                    summary_warnings=summary_warnings,
                    merge_health_warnings_into_summary=False,
                )
                merged_warnings.extend(zw)
    except CloudflareAuthError as e:
        log.error("%s", e)
        return exits.AUTH_FAILED

    report_raw["warnings"] = merged_warnings
    report_raw["zone_health_fetched_at"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    save_report_json(out, report_raw, quiet=opts.quiet)
    return exits.SUCCESS
