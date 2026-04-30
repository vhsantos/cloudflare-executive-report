"""Assemble multi-zone, multi-stream PDF reports."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from reportlab.platypus import PageBreak, Spacer

from cloudflare_executive_report import __version__
from cloudflare_executive_report.cf_client import CloudflareClient
from cloudflare_executive_report.common.constants import (
    PDF_SPACE_SMALL_PT,
    PROJECT_GITHUB_URL,
    PROJECT_NAME,
    PROJECT_PYPI_URL,
)
from cloudflare_executive_report.common.dates import parse_ymd
from cloudflare_executive_report.common.period_resolver import report_type_for_options
from cloudflare_executive_report.config import AppConfig
from cloudflare_executive_report.executive.portfolio import build_portfolio_summary
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
    load_email_for_range,
    load_http_adaptive_for_range,
    load_http_for_range,
    load_security_for_range,
)
from cloudflare_executive_report.pdf.primitives import (
    clear_render_context,
    get_render_context,
    initialize,
)
from cloudflare_executive_report.pdf.streams.appendix import (
    aggregate_nist_reference_rows,
    include_report_appendix,
)
from cloudflare_executive_report.pdf.streams.cache import (
    append_cache_stream,
    collect_cache_appendix_notes,
)
from cloudflare_executive_report.pdf.streams.dns import (
    append_dns_stream,
    collect_dns_appendix_notes,
)
from cloudflare_executive_report.pdf.streams.email import (
    append_email_stream,
    collect_email_appendix_notes,
)
from cloudflare_executive_report.pdf.streams.executive_summary import append_executive_summary
from cloudflare_executive_report.pdf.streams.http import (
    append_http_stream,
    collect_http_appendix_notes,
)
from cloudflare_executive_report.pdf.streams.portfolio import append_portfolio_summary
from cloudflare_executive_report.pdf.streams.security import (
    append_security_stream,
    collect_security_appendix_notes,
)
from cloudflare_executive_report.pdf.theme import (
    Theme,
    theme_with_brand_colors,
    theme_with_chart_format,
    theme_with_map_format,
)
from cloudflare_executive_report.report.baseline_selection import (
    find_previous_zone_in_report,
    select_previous_report_for_period,
)
from cloudflare_executive_report.sync.options import SyncOptions
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
    hist_dir = cfg.history_path()
    if not hist_dir.is_dir():
        return None
    current = cfg.report_current_path().resolve()
    # Prioritize reports matching cf_report_*.json, newest first
    all_files = sorted(
        hist_dir.glob("cf_report_*.json"), key=lambda p: p.stat().st_mtime, reverse=True
    )
    # Exclude current report itself
    candidates = [p for p in all_files if p.resolve() != current]
    if not candidates:
        return None
    try:
        with open(candidates[0], encoding="utf-8") as f:
            return cast(dict[str, Any], json.load(f))
    except (OSError, json.JSONDecodeError):
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
    """
    Generate a PDF report from a JSON snapshot or by fetching data from the cache/API.

    The resulting PDF is written to output_path.
    """
    if theme is not None:
        th = theme_with_map_format(
            theme_with_chart_format(theme, cfg.pdf.chart_format),
            cfg.pdf.map_format,
        )
    else:
        q = parse_pdf_image_quality(cfg.pdf.image_quality)
        th = theme_with_map_format(
            theme_with_chart_format(theme_with_pdf_image_quality(q), cfg.pdf.chart_format),
            cfg.pdf.map_format,
        )
    th = theme_with_brand_colors(
        th,
        primary=cfg.pdf.primary_color,
        accent=cfg.pdf.accent_color,
    )
    cache_root = cfg.cache_path()
    initialize(th)
    try:
        styles = get_render_context().styles
        story: list[Any] = []
        cover_appended = append_cover_page(
            story,
            cover=cfg.cover,
            spec=spec,
            styles=styles,
            theme=th,
        )
        after_cover_insert_index = len(story)
        include_stream_details = cfg.pdf.profile == "detailed"
        include_zone_summary = spec.include_executive_summary and cfg.pdf.profile in (
            "executive",
            "detailed",
        )
        want_portfolio_page = spec.include_executive_summary and len(spec.zone_ids) >= 2
        need_executive_build = spec.include_executive_summary and (
            include_zone_summary or want_portfolio_page
        )
        portfolio_zone_blocks: list[dict[str, Any]] = []
        appendix_zone_summaries: list[dict[str, Any]] = []
        appendix_metric_notes: list[str] = []

        if not spec.include_executive_summary and cfg.pdf.profile != "minimal":
            log.warning(
                "pdf.profile is %r but executive summary is disabled for this PDF; "
                "no per-zone executive sections will be rendered. "
                "Use profile 'minimal' or enable the executive summary.",
                cfg.pdf.profile,
            )

        cache_stream_in_report = any(s.strip().lower() == "cache" for s in spec.streams)

        for zi, zone_key in enumerate(spec.zone_ids):
            zone_id, zone_name = resolve_zone(cfg, zone_key)
            if include_zone_summary or include_stream_details:
                if zi > 0:
                    story.append(PageBreak())
                story.append(Spacer(1, PDF_SPACE_SMALL_PT))

            loaded_dns = None
            loaded_http = None
            loaded_http_adaptive = None
            loaded_dns_records = None
            loaded_audit = None
            loaded_certificates = None
            loaded_security = None
            loaded_cache = None
            loaded_email = None
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
                    appendix_metric_notes.extend(
                        collect_dns_appendix_notes(loaded_dns.rollup, profile=cfg.pdf.profile)
                    )
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
                    appendix_metric_notes.extend(
                        collect_http_appendix_notes(loaded_http.rollup, profile=cfg.pdf.profile)
                    )
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
                    appendix_metric_notes.extend(
                        collect_security_appendix_notes(
                            loaded_security.rollup, profile=cfg.pdf.profile
                        )
                    )
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
                    appendix_metric_notes.extend(
                        collect_cache_appendix_notes(loaded_cache.rollup, profile=cfg.pdf.profile)
                    )
                elif sid == "email":
                    loaded_email = load_email_for_range(
                        cache_root,
                        zone_id,
                        zone_name,
                        spec.start,
                        spec.end,
                        top=spec.top,
                    )
                    zone_warnings.extend(loaded_email.warnings)
                    appendix_metric_notes.extend(
                        collect_email_appendix_notes(loaded_email.rollup, profile=cfg.pdf.profile)
                    )

            snapshot_zone = _find_zone_snapshot(report_snapshot, zone_id)

            # Supplemental streams for executive summary and appendix
            if need_executive_build:
                # http_adaptive is a dependency for the http summary
                if "http" in spec.streams:
                    loaded_http_adaptive = load_http_adaptive_for_range(
                        cache_root,
                        zone_id,
                        zone_name,
                        spec.start,
                        spec.end,
                        top=spec.top,
                    )
                    zone_warnings.extend(loaded_http_adaptive.warnings)

                # dns_records is a dependency for the dns summary
                if "dns" in spec.streams:
                    loaded_dns_records = load_dns_records_for_range(
                        cache_root,
                        zone_id,
                        zone_name,
                        spec.start,
                        spec.end,
                        top=spec.top,
                    )
                    zone_warnings.extend(loaded_dns_records.warnings)

                if "audit" in spec.streams:
                    loaded_audit = load_audit_for_range(
                        cache_root,
                        zone_id,
                        zone_name,
                        spec.start,
                        spec.end,
                        top=spec.top,
                    )
                    zone_warnings.extend(loaded_audit.warnings)

                if "certificates" in spec.streams:
                    loaded_certificates = load_certificates_for_range(
                        cache_root,
                        zone_id,
                        zone_name,
                        spec.start,
                        spec.end,
                        top=spec.top,
                    )
                    zone_warnings.extend(loaded_certificates.warnings)

                if snapshot_zone and isinstance(snapshot_zone.get("executive_summary"), dict):
                    executive_summary = dict(snapshot_zone.get("executive_summary") or {})
                elif report_snapshot is not None:
                    raise ValueError(
                        "Executive summary is not in the report snapshot "
                        f"(zone {zone_name}). Rebuild report JSON first."
                    )
                else:
                    from cloudflare_executive_report.executive.summary import (
                        build_executive_summary,
                    )

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
                            raise ValueError(
                                "Zone health is not in report snapshot and live fetch is disabled "
                                f"(zone {zone_name}). Use a matching cf_report.json or run without "
                                "--cache-only."
                            )

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
                        email=loaded_email.rollup if loaded_email else None,
                        warnings=zone_warnings,
                        as_of_date=parse_ymd(spec.end),
                        current_period={"start": spec.start, "end": spec.end},
                        previous_report=previous_report,
                        previous_zone=find_previous_zone_in_report(previous_report, zone_id),
                        disabled_rules=cfg.executive.disabled_rules,
                    )
                if include_zone_summary:
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
                appendix_zone_summaries.append(executive_summary)
                if want_portfolio_page:
                    portfolio_zone_blocks.append(
                        {
                            "zone_name": zone_name,
                            "zone_id": zone_id,
                            "executive_summary": executive_summary,
                        }
                    )

            if not include_stream_details:
                continue

            for si, stream in enumerate(spec.streams):
                if si > 0 or include_zone_summary:
                    story.append(PageBreak())
                sid = stream.strip().lower()
                if sid == "dns":
                    if loaded_dns is None:
                        continue
                    if snapshot_zone and isinstance(snapshot_zone.get("dns"), dict):
                        loaded_dns.rollup = dict(snapshot_zone.get("dns") or {})
                    if loaded_dns.api_day_count == 0:
                        _warn_skip_no_api_data("DNS", zone_name, spec.start, spec.end)
                        continue
                    append_dns_stream(
                        story,
                        zone_name=zone_name,
                        period_start=spec.start,
                        period_end=spec.end,
                        dns=loaded_dns.rollup,
                        daily_queries=loaded_dns.daily_queries,
                        missing_dates=loaded_dns.missing_dates,
                        layout=spec.dns_layout,
                        theme=th,
                        top=spec.top,
                    )
                elif sid == "http":
                    if loaded_http is None:
                        continue
                    if snapshot_zone and isinstance(snapshot_zone.get("http"), dict):
                        loaded_http.rollup = dict(snapshot_zone.get("http") or {})
                    if loaded_http.api_day_count == 0:
                        _warn_skip_no_api_data("HTTP", zone_name, spec.start, spec.end)
                        continue
                    append_http_stream(
                        story,
                        zone_name=zone_name,
                        period_start=spec.start,
                        period_end=spec.end,
                        http=loaded_http.rollup,
                        daily_requests_cached=loaded_http.daily_requests_cached,
                        daily_requests_uncached=loaded_http.daily_requests_uncached,
                        daily_bytes_cached=loaded_http.daily_bytes_cached,
                        daily_bytes_uncached=loaded_http.daily_bytes_uncached,
                        daily_uniques=loaded_http.daily_uniques,
                        missing_dates=loaded_http.missing_dates,
                        layout=spec.http_layout,
                        theme=th,
                        top=spec.top,
                        cache_stream_in_report=cache_stream_in_report,
                    )
                elif sid == "security":
                    if loaded_security is None:
                        continue
                    if snapshot_zone and isinstance(snapshot_zone.get("security"), dict):
                        loaded_security.rollup = dict(snapshot_zone.get("security") or {})
                    if loaded_security.api_day_count == 0:
                        _warn_skip_no_api_data("Security", zone_name, spec.start, spec.end)
                        continue
                    append_security_stream(
                        story,
                        zone_name=zone_name,
                        period_start=spec.start,
                        period_end=spec.end,
                        security=loaded_security.rollup,
                        daily_security_triple=loaded_security.daily_security_triple,
                        missing_dates=loaded_security.missing_dates,
                        layout=spec.security_layout,
                        theme=th,
                        top=spec.top,
                        cache_stream_in_report=cache_stream_in_report,
                    )
                elif sid == "cache":
                    if loaded_cache is None:
                        continue
                    if snapshot_zone and isinstance(snapshot_zone.get("cache"), dict):
                        loaded_cache.rollup = dict(snapshot_zone.get("cache") or {})
                    if loaded_cache.api_day_count == 0:
                        _warn_skip_no_api_data("Cache", zone_name, spec.start, spec.end)
                        continue
                    append_cache_stream(
                        story,
                        zone_name=zone_name,
                        period_start=spec.start,
                        period_end=spec.end,
                        cache=loaded_cache.rollup,
                        daily_cache_cf_origin=loaded_cache.daily_cache_cf_origin,
                        missing_dates=loaded_cache.missing_dates,
                        layout=spec.cache_layout,
                        theme=th,
                        top=spec.top,
                        http_mime_1d=loaded_cache.http_mime_1d,
                    )
                elif sid == "email":
                    if loaded_email is None:
                        continue
                    if snapshot_zone and isinstance(snapshot_zone.get("email"), dict):
                        loaded_email.rollup = dict(snapshot_zone.get("email") or {})
                    if loaded_email.api_day_count == 0:
                        _warn_skip_no_api_data("Email", zone_name, spec.start, spec.end)
                        continue
                    append_email_stream(
                        story,
                        zone_name=zone_name,
                        period_start=spec.start,
                        period_end=spec.end,
                        email=loaded_email.rollup,
                        daily_forwarded=loaded_email.daily_forwarded,
                        daily_delivery_failed=loaded_email.daily_delivery_failed,
                        daily_dropped_rejected=loaded_email.daily_dropped_rejected,
                        missing_dates=loaded_email.missing_dates,
                        layout=spec.email_layout,
                        theme=th,
                    )
                else:
                    log.warning("Unknown stream %r - skipped", stream)

        if want_portfolio_page and len(portfolio_zone_blocks) >= 2:
            log.debug(
                "Inserting multi-zone portfolio summary for %d zones",
                len(portfolio_zone_blocks),
            )
            portfolio_summary = build_portfolio_summary(
                portfolio_zone_blocks,
                sort_by=cfg.portfolio.sort_by,
            )
            portfolio_story: list[Any] = []
            if cover_appended:
                portfolio_story.append(PageBreak())
            append_portfolio_summary(
                portfolio_story,
                summary=portfolio_summary,
                period_start=spec.start,
                period_end=spec.end,
                theme=th,
            )
            if include_zone_summary or include_stream_details:
                portfolio_story.append(PageBreak())
            story[after_cover_insert_index:after_cover_insert_index] = portfolio_story

        if cfg.executive.include_appendix and appendix_zone_summaries:
            metric_notes = sorted({note.strip() for note in appendix_metric_notes if note.strip()})
            nist_rows = aggregate_nist_reference_rows(appendix_zone_summaries)
            if metric_notes or nist_rows:
                story.append(PageBreak())
                include_report_appendix(
                    story,
                    theme=th,
                    metric_notes=metric_notes,
                    nist_reference_rows=nist_rows,
                )

        if not story:
            msg = "No report content: no cached API data for selected zones and streams."
            raise ValueError(msg)

        generated = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
        footer_left = f"Generated: {generated}"
        if len(spec.zone_ids) == 1:
            _, zone_name_for_title = resolve_zone(cfg, spec.zone_ids[0])
            doc_title = f"{PROJECT_NAME} - {zone_name_for_title}"
        else:
            doc_title = f"{PROJECT_NAME} - {len(spec.zone_ids)} zones"
        stream_list = ", ".join(spec.streams)
        doc_subject = (
            f"Security posture and performance report for {spec.start} to {spec.end}; "
            f"profile={cfg.pdf.profile}; streams={stream_list}; "
            f"GitHub={PROJECT_GITHUB_URL}; "
            f"PyPI={PROJECT_PYPI_URL}"
        )
        metadata = {
            "title": doc_title,
            "subject": doc_subject,
            "author": f"{PROJECT_NAME} v{__version__}",
            "creator": PROJECT_NAME,
            "producer": PROJECT_NAME,
            "keywords": (
                "Cloudflare, security, executive report, NIST, PDF, "
                f"{PROJECT_GITHUB_URL}, "
                f"{PROJECT_PYPI_URL}"
            ),
        }
        footer = footer_canvas_factory(theme=th, left_text=footer_left)
        first_page_canvas = (lambda _canvas, _doc: None) if cover_appended else footer

        doc = build_simple_doc(
            str(output_path),
            theme=th,
            title=doc_title,
            subject=doc_subject,
            author=metadata["author"],
            creator=metadata["creator"],
            producer=metadata["producer"],
            keywords=metadata["keywords"],
        )
        doc.build(story, onFirstPage=first_page_canvas, onLaterPages=footer)
        log.info("Wrote PDF %s", output_path.resolve())
    finally:
        clear_render_context()
