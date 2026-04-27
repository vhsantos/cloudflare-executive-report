"""Update per-zone blocks inside report JSON (health and executive summary)."""

from __future__ import annotations

from datetime import date
from typing import Any

from cloudflare_executive_report.cf_client import CloudflareClient
from cloudflare_executive_report.common.dates import parse_ymd
from cloudflare_executive_report.config import AppConfig
from cloudflare_executive_report.executive.summary import build_executive_summary
from cloudflare_executive_report.report.baseline_selection import (
    find_previous_zone_in_report,
    select_previous_report_for_period,
)
from cloudflare_executive_report.sync.options import SyncOptions
from cloudflare_executive_report.zone_health import fetch_zone_health


def optional_dict_section(zone_block: dict[str, Any], key: str) -> dict[str, Any] | None:
    """Return zone_block[key] when it is a dict, else None."""
    value = zone_block.get(key)
    return value if isinstance(value, dict) else None


def update_zone_json_block_health_and_executive(
    *,
    cfg: AppConfig,
    opts: SyncOptions,
    client: CloudflareClient,
    zone_id: str,
    zone_name: str,
    zone_meta: dict[str, Any],
    zone_block: dict[str, Any],
    report_start: str,
    report_end: str,
    y: date,
    summary_warnings: list[str],
    merge_health_warnings_into_summary: bool = True,
) -> list[str]:
    """Set zone_health and executive_summary on zone_block.

    When merge_health_warnings_into_summary is True (full JSON build), health warnings are
    appended to summary_warnings before building the executive summary. When False (health-only
    JSON refresh), executive summary uses an empty warning list while zw is still returned.

    Returns warnings from fetch_zone_health.
    """
    zh, zw = fetch_zone_health(
        client,
        zone_id,
        zone_name,
        skip=opts.skip_zone_health,
        zone_meta=zone_meta,
    )
    zone_block["zone_health"] = zh
    if merge_health_warnings_into_summary:
        summary_warnings.extend(zw)
    warnings_for_executive = list(summary_warnings) if merge_health_warnings_into_summary else []
    previous_report = select_previous_report_for_period(
        cfg,
        current_start=report_start,
        current_end=report_end,
        zone_id=zone_id,
        opts=opts,
        y=y,
    )
    zone_block["executive_summary"] = build_executive_summary(
        zone_id=zone_id,
        zone_name=zone_name,
        zone_health=zh,
        dns=optional_dict_section(zone_block, "dns"),
        http=optional_dict_section(zone_block, "http"),
        security=optional_dict_section(zone_block, "security"),
        cache=optional_dict_section(zone_block, "cache"),
        http_adaptive=optional_dict_section(zone_block, "http_adaptive"),
        dns_records=optional_dict_section(zone_block, "dns_records"),
        audit=optional_dict_section(zone_block, "audit"),
        certificates=optional_dict_section(zone_block, "certificates"),
        warnings=warnings_for_executive,
        as_of_date=parse_ymd(report_end),
        current_period={"start": report_start, "end": report_end},
        previous_report=previous_report,
        previous_zone=find_previous_zone_in_report(previous_report, zone_id),
        disabled_rules=cfg.executive.disabled_rules,
        email=optional_dict_section(zone_block, "email"),
    )
    return zw
