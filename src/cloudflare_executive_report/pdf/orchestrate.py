"""Assemble multi-zone, multi-stream PDF reports."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from reportlab.platypus import PageBreak, Paragraph, Spacer

from cloudflare_executive_report import __version__
from cloudflare_executive_report.config import AppConfig
from cloudflare_executive_report.pdf.document import build_simple_doc, footer_canvas_factory
from cloudflare_executive_report.pdf.figure_quality import (
    parse_pdf_image_quality,
    theme_with_pdf_image_quality,
)
from cloudflare_executive_report.pdf.layout_spec import ReportSpec
from cloudflare_executive_report.pdf.loader import load_dns_for_range, load_http_for_range
from cloudflare_executive_report.pdf.primitives import make_styles
from cloudflare_executive_report.pdf.streams.dns import append_dns_stream
from cloudflare_executive_report.pdf.streams.http import append_http_stream
from cloudflare_executive_report.pdf.theme import Theme

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


def write_report_pdf(
    output_path: Path,
    cfg: AppConfig,
    spec: ReportSpec,
    *,
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

    for zi, zone_key in enumerate(spec.zone_ids):
        zone_id, zone_name = resolve_zone(cfg, zone_key)
        if zi > 0:
            story.append(PageBreak())
        story.append(
            Paragraph(
                f"<font color='{th.slate}'><b>{zone_name}</b></font> "
                f"<font color='{th.muted}'>({zone_id})</font>",
                styles["RepZoneTitle"],
            )
        )
        story.append(Spacer(1, 6))

        for si, stream in enumerate(spec.streams):
            if si > 0:
                story.append(PageBreak())
            sid = stream.strip().lower()
            if sid == "dns":
                loaded = load_dns_for_range(
                    cache_root,
                    zone_id,
                    zone_name,
                    spec.start,
                    spec.end,
                    top=spec.top,
                )
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
                loaded = load_http_for_range(
                    cache_root,
                    zone_id,
                    zone_name,
                    spec.start,
                    spec.end,
                    top=spec.top,
                )
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
            else:
                log.warning("Unknown stream %r - skipped", stream)

    if not story:
        msg = "No report content: no cached API data for selected zones and streams."
        raise ValueError(msg)

    generated = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    zone_label = ", ".join(resolve_zone(cfg, z)[1] for z in spec.zone_ids)
    footer_left = f"{zone_label} · {spec.start}-{spec.end} (UTC) · Generated {generated}"
    footer = footer_canvas_factory(theme=th, left_text=footer_left, tool_version=__version__)

    doc = build_simple_doc(str(output_path), theme=th, title="Analytics report")
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    log.info("Wrote PDF %s", output_path.resolve())
