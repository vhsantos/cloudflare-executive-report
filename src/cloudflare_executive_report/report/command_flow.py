"""High-level branching for ``cf-report report`` (snapshot reuse, sync, health refresh, PDF)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cloudflare_executive_report import exits
from cloudflare_executive_report.common.period_resolver import build_data_fingerprint
from cloudflare_executive_report.common.report_cache import report_period_streams_cache_complete
from cloudflare_executive_report.common.report_snapshot import (
    data_fingerprint_matches,
    is_report_snapshot_valid,
)
from cloudflare_executive_report.config import AppConfig
from cloudflare_executive_report.report.health_refresh import refresh_report_json_zone_health_only
from cloudflare_executive_report.report.period import pdf_report_period_for_options
from cloudflare_executive_report.report.snapshot import load_report_json
from cloudflare_executive_report.sync.options import SyncOptions
from cloudflare_executive_report.sync.orchestrator import run_sync

log = logging.getLogger(__name__)

_CACHE_ONLY_SNAPSHOT_MSG = (
    "Error: No matching report snapshot for this request. "
    "Run `cf-report report` without --cache-only first, then retry."
)


@dataclass(frozen=True)
class ReportPdfOutcome:
    """Result of a report PDF run (CLI maps this to exit code and messages)."""

    exit_code: int
    stderr: str | None = None
    pdf_written_line: str | None = None


def run_report_pdf_command(
    *,
    cfg: AppConfig,
    sync_opts: SyncOptions,
    output: Path,
    zone_effective: str | None,
    zone_keys: list[str],
    scoped_zone_ids: list[str],
    pdf_streams: tuple[str, ...],
    top: int,
    type_set: frozenset[str],
    include_today: bool,
    cache_only: bool,
    refresh_health: bool,
) -> ReportPdfOutcome:
    """Execute report flow: optional sync/health refresh, then write PDF."""
    try:
        period_start, period_end = pdf_report_period_for_options(
            cfg, sync_opts, zone_filter=zone_effective
        )
    except ValueError as e:
        return ReportPdfOutcome(exit_code=exits.INVALID_PARAMS, stderr=str(e))

    requested_fingerprint = build_data_fingerprint(
        start=period_start,
        end=period_end,
        zones=scoped_zone_ids,
        top=top,
        types=type_set,
        include_today=include_today,
    )
    current_report = load_report_json(cfg.report_current_path())
    snapshot_valid = is_report_snapshot_valid(current_report)
    fingerprint_ok = data_fingerprint_matches(current_report, requested_fingerprint)

    def write_pdf(
        snapshot: dict[str, Any] | None,
        *,
        allow_live_health: bool,
        span: tuple[str, str],
    ) -> ReportPdfOutcome:
        ps, pe = span
        try:
            from cloudflare_executive_report.pdf.layout_spec import ReportSpec
            from cloudflare_executive_report.pdf.orchestrate import write_report_pdf
        except ImportError as e:
            return ReportPdfOutcome(
                exit_code=exits.GENERAL_ERROR,
                stderr=f"Failed to import PDF report modules: {e}",
            )
        spec = ReportSpec(
            zone_ids=zone_keys,
            start=ps,
            end=pe,
            streams=pdf_streams,
            top=top,
        )
        try:
            write_report_pdf(
                output.resolve(),
                cfg,
                spec,
                sync_opts=sync_opts,
                report_snapshot=snapshot,
                allow_live_health_fetch=allow_live_health,
            )
        except ValueError as e:
            return ReportPdfOutcome(exit_code=exits.INVALID_PARAMS, stderr=str(e))
        except Exception as e:
            return ReportPdfOutcome(
                exit_code=exits.GENERAL_ERROR, stderr=f"PDF generation failed: {e}"
            )
        return ReportPdfOutcome(
            exit_code=exits.SUCCESS,
            pdf_written_line=f"Wrote {output.resolve()}",
        )

    initial_span = (period_start, period_end)

    if cache_only:
        if not snapshot_valid or not fingerprint_ok:
            return ReportPdfOutcome(exit_code=exits.INVALID_PARAMS, stderr=_CACHE_ONLY_SNAPSHOT_MSG)
        if refresh_health:
            if not report_period_streams_cache_complete(
                cfg,
                sync_opts,
                zone_filter=zone_effective,
                streams=pdf_streams,
            ):
                return ReportPdfOutcome(
                    exit_code=exits.INVALID_PARAMS,
                    stderr=(
                        "Error: --cache-only --refresh-health requires complete cached stream data "
                        "for the report period (PDF streams). "
                        "Run `cf-report sync` to fill the cache."
                    ),
                )
            code = refresh_report_json_zone_health_only(
                cfg,
                sync_opts,
                zone_filter=zone_effective,
            )
            if code != exits.SUCCESS:
                return ReportPdfOutcome(exit_code=code)
            refreshed = load_report_json(cfg.report_current_path())
            if refreshed is None or not is_report_snapshot_valid(refreshed):
                return ReportPdfOutcome(
                    exit_code=exits.GENERAL_ERROR,
                    stderr="Error: report JSON missing or invalid after health refresh.",
                )
            if refreshed.get("partial") is True:
                log.warning(
                    "Snapshot has missing stream days (partial=true); see missing_days in JSON."
                )
            return write_pdf(refreshed, allow_live_health=False, span=initial_span)
        if current_report is not None and current_report.get("partial") is True:
            log.warning(
                "Snapshot has missing stream days (partial=true); see missing_days in JSON."
            )
        return write_pdf(current_report, allow_live_health=False, span=initial_span)

    if snapshot_valid and fingerprint_ok and not refresh_health:
        if current_report is not None and current_report.get("partial") is True:
            log.warning(
                "Snapshot has missing stream days (partial=true); see missing_days in JSON."
            )
        return write_pdf(current_report, allow_live_health=False, span=initial_span)

    if snapshot_valid and fingerprint_ok and refresh_health:
        if report_period_streams_cache_complete(
            cfg,
            sync_opts,
            zone_filter=zone_effective,
            streams=pdf_streams,
        ):
            code = refresh_report_json_zone_health_only(
                cfg,
                sync_opts,
                zone_filter=zone_effective,
            )
            if code != exits.SUCCESS:
                return ReportPdfOutcome(exit_code=code)
            refreshed = load_report_json(cfg.report_current_path())
            if refreshed is None or not is_report_snapshot_valid(refreshed):
                return ReportPdfOutcome(
                    exit_code=exits.GENERAL_ERROR,
                    stderr="Error: report JSON missing or invalid after health refresh.",
                )
            return write_pdf(refreshed, allow_live_health=False, span=initial_span)
        code = run_sync(
            cfg,
            sync_opts,
            zone_filter=zone_effective,
            output_path=None,
            write_stdout=False,
        )
        if code != exits.SUCCESS:
            return ReportPdfOutcome(exit_code=code)
        try:
            period_start, period_end = pdf_report_period_for_options(
                cfg, sync_opts, zone_filter=zone_effective
            )
        except ValueError as e:
            return ReportPdfOutcome(exit_code=exits.INVALID_PARAMS, stderr=str(e))
        return write_pdf(None, allow_live_health=True, span=(period_start, period_end))

    code = run_sync(
        cfg,
        sync_opts,
        zone_filter=zone_effective,
        output_path=None,
        write_stdout=False,
    )
    if code != exits.SUCCESS:
        return ReportPdfOutcome(exit_code=code)
    try:
        period_start, period_end = pdf_report_period_for_options(
            cfg, sync_opts, zone_filter=zone_effective
        )
    except ValueError as e:
        return ReportPdfOutcome(exit_code=exits.INVALID_PARAMS, stderr=str(e))
    return write_pdf(None, allow_live_health=True, span=(period_start, period_end))
