"""High-level branching for ``cf-report report`` (snapshot reuse, sync, health refresh, PDF)."""

from __future__ import annotations

import logging
import smtplib
import ssl
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cloudflare_executive_report import exits
from cloudflare_executive_report.common.period_resolver import build_data_fingerprint
from cloudflare_executive_report.common.report_cache import report_period_streams_cache_complete
from cloudflare_executive_report.config import AppConfig
from cloudflare_executive_report.report.health_refresh import (
    refresh_snapshot_zone_health,
)
from cloudflare_executive_report.report.period import pdf_report_period_for_options
from cloudflare_executive_report.report.snapshot import find_and_extract_reusable_snapshot
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
    email_sent_line: str | None = None


def _finalize_pdf_and_optional_email(
    *,
    cfg: AppConfig,
    output: Path,
    period_start: str,
    period_end: str,
    zone_keys: list[str],
    send_email: bool,
    pdf_written_line: str | None,
) -> ReportPdfOutcome:
    """Return success outcome, optionally sending the PDF via SMTP."""
    if not send_email:
        return ReportPdfOutcome(
            exit_code=exits.SUCCESS,
            pdf_written_line=pdf_written_line,
        )
    if not cfg.email.enabled:
        return ReportPdfOutcome(
            exit_code=exits.INVALID_PARAMS,
            stderr="Error: --email requires email.enabled: true in config.",
        )
    from cloudflare_executive_report.email.smtp import send_pdf_report_email

    try:
        send_pdf_report_email(
            cfg.email,
            pdf_path=output.resolve(),
            period_start=period_start,
            period_end=period_end,
            zone_count=len(zone_keys),
        )
    except ValueError as e:
        return ReportPdfOutcome(exit_code=exits.INVALID_PARAMS, stderr=str(e))
    except (OSError, smtplib.SMTPException, ssl.SSLError) as e:
        return ReportPdfOutcome(
            exit_code=exits.GENERAL_ERROR,
            stderr=f"Email send failed: {e}",
        )
    shown = ", ".join(r.strip() for r in cfg.email.recipients if str(r).strip())
    if len(shown) > 200:
        shown = shown[:197] + "..."
    return ReportPdfOutcome(
        exit_code=exits.SUCCESS,
        pdf_written_line=pdf_written_line,
        email_sent_line=f"Sent report by email to {shown}",
    )


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
    send_email: bool = False,
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
        top=top,
        types=type_set,
        include_today=include_today,
    )

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
        return _finalize_pdf_and_optional_email(
            cfg=cfg,
            output=output,
            period_start=ps,
            period_end=pe,
            zone_keys=zone_keys,
            send_email=send_email,
            pdf_written_line=f"Wrote {output.resolve()}",
        )

    initial_span = (period_start, period_end)

    if cache_only:
        reusable_snapshot = find_and_extract_reusable_snapshot(
            cfg, requested_fingerprint, scoped_zone_ids
        )
        if not reusable_snapshot:
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
            code = refresh_snapshot_zone_health(
                cfg,
                sync_opts,
                zone_filter=zone_effective,
                snapshot_data=reusable_snapshot,
            )
            if code != exits.SUCCESS:
                return ReportPdfOutcome(exit_code=code)
            if reusable_snapshot.get("partial") is True:
                log.warning(
                    "Snapshot has missing stream days (partial=true); see missing_days in JSON."
                )
            return write_pdf(reusable_snapshot, allow_live_health=False, span=initial_span)
        if reusable_snapshot.get("partial") is True:
            log.warning(
                "Snapshot has missing stream days (partial=true); see missing_days in JSON."
            )
        return write_pdf(reusable_snapshot, allow_live_health=False, span=initial_span)

    # Normal Mode (Design A): Always run sync to process from raw cache
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
