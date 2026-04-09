"""Assemble multi-zone, multi-stream PDF reports."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from reportlab.platypus import PageBreak, Spacer

from cloudflare_executive_report.cf_client import CloudflareClient
from cloudflare_executive_report.common.period_resolver import report_type_for_options
from cloudflare_executive_report.config import AppConfig
from cloudflare_executive_report.dates import parse_ymd
from cloudflare_executive_report.executive.summary import build_executive_summary
from cloudflare_executive_report.pdf.cover import append_cover_page
from cloudflare_executive_report.pdf.document import build_simple_doc, footer_canvas_factory
from cloudflare_executive_report.pdf.figure_quality import (
    parse_pdf_image_quality,
    theme_with_pdf_image_quality,
)
from cloudflare_executive_report.pdf.layout_spec import ReportSpec
from cloudflare_executive_report.pdf.loader import (
    load_audit_for_range,
    load_cache_for_range,
    load_certificates_for_range,
    load_dns_for_range,
    load_dns_records_for_range,
    load_http_adaptive_for_range,
    load_http_for_range,
    load_security_for_range,
)
from cloudflare_executive_report.pdf.primitives import make_styles
from cloudflare_executive_report.pdf.streams.cache import append_cache_stream
from cloudflare_executive_report.pdf.streams.dns import append_dns_stream
from cloudflare_executive_report.pdf.streams.executive_summary import append_executive_summary
from cloudflare_executive_report.pdf.streams.http import append_http_stream
from cloudflare_executive_report.pdf.streams.security import append_security_stream
from cloudflare_executive_report.pdf.theme import Theme
from cloudflare_executive_report.sync.options import SyncOptions
from cloudflare_executive_report.sync.orchestrator import select_previous_report_for_period
from cloudflare_executive_report.zone_health import fetch_zone_health

log = logging.getLogger(__name__)


def _warn_skip_no_api_data(section: str, zone_name: str, start: str, end: str) -> None:
    log.warning(
        "Skipping %s section: no API data for zone %s in %s..%s",
        section,
        zone_name,
        start,
        end,
    )


def resolve_zone(cfg: AppConfig, key: str) -> tuple[str, str]:
    key = key.strip()
    for z in cfg.zones:
        if z.id == key or z.name == key:
            return z.id, z.name
    return key, key


def _load_previous_report(cfg: AppConfig) -> dict[str, Any] | None:
    path = cfg.report_previous_path()
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _find_previous_zone(
    previous_report: dict[str, Any] | None, zone_id: str
) -> dict[str, Any] | None:
    if not isinstance(previous_report, dict):
        return None
    for zone in previous_report.get("zones") or []:
        if isinstance(zone, dict) and str(zone.get("zone_id") or "") == zone_id:
            return zone
    return None


def _find_zone_snapshot(
    report_snapshot: dict[str, Any] | None, zone_id: str
) -> dict[str, Any] | None:
    if not isinstance(report_snapshot, dict):
        return None
    for zone in report_snapshot.get("zones") or []:
        if isinstance(zone, dict) and str(zone.get("zone_id") or "") == zone_id:
            return zone
    return None


def _report_type_for_pdf(
    *,
    report_snapshot: dict[str, Any] | None,
    sync_opts: SyncOptions | None,
) -> str | None:
    if isinstance(report_snapshot, dict):
        raw = str(report_snapshot.get("report_type") or "").strip()
        if raw:
            return raw
    if sync_opts is not None:
        return report_type_for_options(sync_opts)
    return None


def write_report_pdf(
    output_path: Path,
    cfg: AppConfig,
    spec: ReportSpec,
    *,
    sync_opts: SyncOptions | None = None,
    report_snapshot: dict[str, Any] | None = None,
    allow_live_health_fetch: bool = True,
    theme: Theme | None = None,
) -> None:
    if theme is not None:
        th = theme
    else:
        q = parse_pdf_image_quality(cfg.pdf_image_quality)
        th = theme_with_pdf_image_quality(q)
    cache_root = cfg.cache_path()
    styles = make_styles(th)
    story: list[Any] = []
    append_cover_page(story, cover=cfg.cover, spec=spec, styles=styles, theme=th)

    cache_stream_in_report = any(s.strip().lower() == "cache" for s in spec.streams)

    for zi, zone_key in enumerate(spec.zone_ids):
        zone_id, zone_name = resolve_zone(cfg, zone_key)
        if zi > 0:
            story.append(PageBreak())
        story.append(Spacer(1, 6))

        loaded_dns = None
        loaded_http = None
        loaded_http_adaptive = None
        loaded_dns_records = None
        loaded_audit = None
        loaded_certificates = None
        loaded_security = None
        loaded_cache = None
        zone_warnings: list[str] = []

        for stream in spec.streams:
            sid = stream.strip().lower()
            if sid == "dns":
                loaded_dns = load_dns_for_range(
                    cache_root,
                    zone_id,
                    zone_name,
                    spec.start,
                    spec.end,
                    top=spec.top,
                )
                zone_warnings.extend(loaded_dns.warnings)
            elif sid == "http":
                loaded_http = load_http_for_range(
                    cache_root,
                    zone_id,
                    zone_name,
                    spec.start,
                    spec.end,
                    top=spec.top,
                )
                zone_warnings.extend(loaded_http.warnings)
            elif sid == "security":
                loaded_security = load_security_for_range(
                    cache_root,
                    zone_id,
                    zone_name,
                    spec.start,
                    spec.end,
                    top=spec.top,
                )
                zone_warnings.extend(loaded_security.warnings)
            elif sid == "cache":
                loaded_cache = load_cache_for_range(
                    cache_root,
                    zone_id,
                    zone_name,
                    spec.start,
                    spec.end,
                    top=spec.top,
                )
                zone_warnings.extend(loaded_cache.warnings)

        if spec.include_executive_summary:
            loaded_http_adaptive = load_http_adaptive_for_range(
                cache_root,
                zone_id,
                zone_name,
                spec.start,
                spec.end,
                top=spec.top,
            )
            zone_warnings.extend(loaded_http_adaptive.warnings)
            loaded_dns_records = load_dns_records_for_range(
                cache_root,
                zone_id,
                zone_name,
                spec.start,
                spec.end,
                top=spec.top,
            )
            zone_warnings.extend(loaded_dns_records.warnings)
            loaded_audit = load_audit_for_range(
                cache_root,
                zone_id,
                zone_name,
                spec.start,
                spec.end,
                top=spec.top,
            )
            zone_warnings.extend(loaded_audit.warnings)
            loaded_certificates = load_certificates_for_range(
                cache_root,
                zone_id,
                zone_name,
                spec.start,
                spec.end,
                top=spec.top,
            )
            zone_warnings.extend(loaded_certificates.warnings)

        snapshot_zone = _find_zone_snapshot(report_snapshot, zone_id)
        zone_health: dict[str, Any]
        health_warnings: list[str] = []
        if snapshot_zone and isinstance(snapshot_zone.get("zone_health"), dict):
            zone_health = dict(snapshot_zone.get("zone_health") or {})
        else:
            if allow_live_health_fetch:
                with CloudflareClient(cfg.api_token) as client:
                    zone_health, health_warnings = fetch_zone_health(
                        client, zone_id, zone_name, skip=False
                    )
                zone_warnings.extend(health_warnings)
            else:
                zone_health = {
                    "zone_name": zone_name,
                    "zone_status": "unknown",
                    "ssl_mode": "unknown",
                    "always_use_https": None,
                    "waf_enabled": None,
                    "dnssec_status": "unknown",
                    "min_tls_version": None,
                    "under_attack_mode": None,
                    "caching_level": None,
                    "edge_cert_status": None,
                }
                zone_warnings.append(
                    "Zone health unavailable in offline mode (no reusable snapshot found)."
                )

        if spec.include_executive_summary:
            if sync_opts is None:
                previous_report = _load_previous_report(cfg)
            else:
                previous_report = select_previous_report_for_period(
                    cfg,
                    current_start=spec.start,
                    current_end=spec.end,
                    zone_id=zone_id,
                    opts=sync_opts,
                )
            if snapshot_zone and isinstance(snapshot_zone.get("executive_summary"), dict):
                executive_summary = dict(snapshot_zone.get("executive_summary") or {})
            else:
                executive_summary = build_executive_summary(
                    zone_id=zone_id,
                    zone_name=zone_name,
                    zone_health=zone_health,
                    dns=loaded_dns.rollup if loaded_dns else None,
                    http=loaded_http.rollup if loaded_http else None,
                    security=loaded_security.rollup if loaded_security else None,
                    cache=loaded_cache.rollup if loaded_cache else None,
                    http_adaptive=loaded_http_adaptive.rollup if loaded_http_adaptive else None,
                    dns_records=loaded_dns_records.rollup if loaded_dns_records else None,
                    audit=loaded_audit.rollup if loaded_audit else None,
                    certificates=loaded_certificates.rollup if loaded_certificates else None,
                    warnings=zone_warnings,
                    as_of_date=parse_ymd(spec.end),
                    current_period={"start": spec.start, "end": spec.end},
                    previous_report=previous_report,
                    previous_zone=_find_previous_zone(previous_report, zone_id),
                )
            append_executive_summary(
                story,
                zone_name=zone_name,
                period_start=spec.start,
                period_end=spec.end,
                summary=executive_summary,
                report_type=_report_type_for_pdf(
                    report_snapshot=report_snapshot,
                    sync_opts=sync_opts,
                ),
                theme=th,
            )

        for si, stream in enumerate(spec.streams):
            if si > 0 or spec.include_executive_summary:
                story.append(PageBreak())
            sid = stream.strip().lower()
            if sid == "dns":
                loaded = loaded_dns
                if loaded is None:
                    continue
                if snapshot_zone and isinstance(snapshot_zone.get("dns"), dict):
                    loaded.rollup = dict(snapshot_zone.get("dns") or {})
                if loaded.api_day_count == 0:
                    _warn_skip_no_api_data("DNS", zone_name, spec.start, spec.end)
                    continue
                append_dns_stream(
                    story,
                    zone_name=zone_name,
                    period_start=spec.start,
                    period_end=spec.end,
                    dns=loaded.rollup,
                    daily_queries=loaded.daily_queries,
                    missing_dates=loaded.missing_dates,
                    layout=spec.dns_layout,
                    theme=th,
                    top=spec.top,
                )
            elif sid == "http":
                loaded = loaded_http
                if loaded is None:
                    continue
                if snapshot_zone and isinstance(snapshot_zone.get("http"), dict):
                    loaded.rollup = dict(snapshot_zone.get("http") or {})
                if loaded.api_day_count == 0:
                    _warn_skip_no_api_data("HTTP", zone_name, spec.start, spec.end)
                    continue
                append_http_stream(
                    story,
                    zone_name=zone_name,
                    period_start=spec.start,
                    period_end=spec.end,
                    http=loaded.rollup,
                    daily_requests_cached=loaded.daily_requests_cached,
                    daily_requests_uncached=loaded.daily_requests_uncached,
                    daily_bytes_cached=loaded.daily_bytes_cached,
                    daily_bytes_uncached=loaded.daily_bytes_uncached,
                    daily_uniques=loaded.daily_uniques,
                    missing_dates=loaded.missing_dates,
                    layout=spec.http_layout,
                    theme=th,
                    top=spec.top,
                )
            elif sid == "security":
                loaded = loaded_security
                if loaded is None:
                    continue
                if snapshot_zone and isinstance(snapshot_zone.get("security"), dict):
                    loaded.rollup = dict(snapshot_zone.get("security") or {})
                if loaded.api_day_count == 0:
                    _warn_skip_no_api_data("Security", zone_name, spec.start, spec.end)
                    continue
                append_security_stream(
                    story,
                    zone_name=zone_name,
                    period_start=spec.start,
                    period_end=spec.end,
                    security=loaded.rollup,
                    daily_security_triple=loaded.daily_security_triple,
                    missing_dates=loaded.missing_dates,
                    layout=spec.security_layout,
                    theme=th,
                    top=spec.top,
                    cache_stream_in_report=cache_stream_in_report,
                )
            elif sid == "cache":
                loaded = loaded_cache
                if loaded is None:
                    continue
                if snapshot_zone and isinstance(snapshot_zone.get("cache"), dict):
                    loaded.rollup = dict(snapshot_zone.get("cache") or {})
                if loaded.api_day_count == 0:
                    _warn_skip_no_api_data("Cache", zone_name, spec.start, spec.end)
                    continue
                append_cache_stream(
                    story,
                    zone_name=zone_name,
                    period_start=spec.start,
                    period_end=spec.end,
                    cache=loaded.rollup,
                    daily_cache_cf_origin=loaded.daily_cache_cf_origin,
                    missing_dates=loaded.missing_dates,
                    layout=spec.cache_layout,
                    theme=th,
                    top=spec.top,
                    http_mime_1d=loaded.http_mime_1d,
                )
            else:
                log.warning("Unknown stream %r - skipped", stream)

    if not story:
        msg = "No report content: no cached API data for selected zones and streams."
        raise ValueError(msg)

    generated = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    footer_left = f"Generated: {generated}"
    footer = footer_canvas_factory(theme=th, left_text=footer_left)

    doc = build_simple_doc(str(output_path), theme=th, title="Analytics report")
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    log.info("Wrote PDF %s", output_path.resolve())
