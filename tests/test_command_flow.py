"""Unit tests for report/command_flow.py."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cloudflare_executive_report import exits
from cloudflare_executive_report.config import AppConfig, ZoneEntry
from cloudflare_executive_report.report.command_flow import (
    ReportPdfOutcome,
    _finalize_pdf_and_optional_email,
    run_report_pdf_command,
)
from cloudflare_executive_report.sync.options import SyncMode, SyncOptions


@pytest.fixture
def mock_cfg(tmp_path: Path) -> AppConfig:
    return AppConfig(
        api_token="x",
        cache_dir=str(tmp_path / "cache"),
        output_dir=str(tmp_path / "output"),
        zones=[ZoneEntry(id="z1", name="n1")],
    )


def test_finalize_pdf_and_optional_email_no_email(mock_cfg: AppConfig) -> None:
    res = _finalize_pdf_and_optional_email(
        cfg=mock_cfg,
        output=Path("test.pdf"),
        period_start="2026-04-01",
        period_end="2026-04-01",
        zone_keys=["z1"],
        send_email=False,
        pdf_written_line="Wrote test.pdf",
    )
    assert res.exit_code == exits.SUCCESS
    assert res.pdf_written_line == "Wrote test.pdf"
    assert res.email_sent_line is None


@patch("cloudflare_executive_report.email.smtp.send_pdf_report_email")
def test_finalize_pdf_and_optional_email_success(mock_send: MagicMock, mock_cfg: AppConfig) -> None:
    mock_cfg.email.enabled = True
    mock_cfg.email.recipients = ["test@example.com"]
    res = _finalize_pdf_and_optional_email(
        cfg=mock_cfg,
        output=Path("test.pdf"),
        period_start="2026-04-01",
        period_end="2026-04-01",
        zone_keys=["z1"],
        send_email=True,
        pdf_written_line="Wrote test.pdf",
    )
    assert res.exit_code == exits.SUCCESS
    assert "Sent report" in res.email_sent_line
    mock_send.assert_called_once()


@patch("cloudflare_executive_report.report.command_flow.pdf_report_period_for_options")
@patch("cloudflare_executive_report.report.command_flow.load_report_json")
@patch("cloudflare_executive_report.report.command_flow.is_report_snapshot_valid")
@patch("cloudflare_executive_report.report.command_flow.data_fingerprint_matches")
@patch("cloudflare_executive_report.report.command_flow._finalize_pdf_and_optional_email")
@patch("cloudflare_executive_report.pdf.orchestrate.write_report_pdf")
def test_run_report_pdf_command_reuse_snapshot(
    mock_write_pdf: MagicMock,
    mock_finalize: MagicMock,
    mock_fingerprint_matches: MagicMock,
    mock_snapshot_valid: MagicMock,
    mock_load_json: MagicMock,
    mock_period: MagicMock,
    mock_cfg: AppConfig,
) -> None:
    mock_period.return_value = ("2026-04-01", "2026-04-01")
    mock_load_json.return_value = {"partial": False}
    mock_snapshot_valid.return_value = True
    mock_fingerprint_matches.return_value = True
    mock_finalize.return_value = ReportPdfOutcome(exit_code=0)

    sync_opts = SyncOptions(mode=SyncMode.last_n, last_n=1)

    res = run_report_pdf_command(
        cfg=mock_cfg,
        sync_opts=sync_opts,
        output=Path("out.pdf"),
        zone_effective=None,
        zone_keys=["z1"],
        scoped_zone_ids=["z1"],
        pdf_streams=("http",),
        top=5,
        type_set=frozenset(["http"]),
        include_today=False,
        cache_only=False,
        refresh_health=False,
    )

    assert res.exit_code == 0
    # is_report_snapshot_valid is called, and since it matches, we go straight to write_pdf
    assert mock_snapshot_valid.called
    assert mock_finalize.called


@patch("cloudflare_executive_report.report.command_flow.pdf_report_period_for_options")
@patch("cloudflare_executive_report.report.command_flow.load_report_json")
@patch("cloudflare_executive_report.report.command_flow.is_report_snapshot_valid")
@patch("cloudflare_executive_report.report.command_flow.run_sync")
@patch("cloudflare_executive_report.report.command_flow._finalize_pdf_and_optional_email")
@patch("cloudflare_executive_report.pdf.orchestrate.write_report_pdf")
def test_run_report_pdf_command_sync_needed(
    mock_write_pdf: MagicMock,
    mock_finalize: MagicMock,
    mock_snapshot_valid: MagicMock,
    mock_sync: MagicMock,
    mock_load_json: MagicMock,
    mock_period: MagicMock,
    mock_cfg: AppConfig,
) -> None:
    mock_period.return_value = ("2026-04-01", "2026-04-01")
    mock_load_json.return_value = None
    mock_snapshot_valid.return_value = False
    mock_sync.return_value = exits.SUCCESS
    mock_finalize.return_value = ReportPdfOutcome(exit_code=0)

    sync_opts = SyncOptions(mode=SyncMode.last_n, last_n=1)

    res = run_report_pdf_command(
        cfg=mock_cfg,
        sync_opts=sync_opts,
        output=Path("out.pdf"),
        zone_effective=None,
        zone_keys=["z1"],
        scoped_zone_ids=["z1"],
        pdf_streams=("http",),
        top=5,
        type_set=frozenset(["http"]),
        include_today=False,
        cache_only=False,
        refresh_health=False,
    )

    assert res.exit_code == 0
    assert mock_sync.called
    assert mock_finalize.called


def test_finalize_pdf_and_optional_email_disabled(mock_cfg: AppConfig) -> None:
    mock_cfg.email.enabled = False
    res = _finalize_pdf_and_optional_email(
        cfg=mock_cfg,
        output=Path("test.pdf"),
        period_start="2026-04-01",
        period_end="2026-04-01",
        zone_keys=["z1"],
        send_email=True,
        pdf_written_line="Wrote test.pdf",
    )
    assert res.exit_code == exits.INVALID_PARAMS
    assert "requires email.enabled: true" in res.stderr


@patch("cloudflare_executive_report.email.smtp.send_pdf_report_email")
def test_finalize_pdf_and_optional_email_error(mock_send: MagicMock, mock_cfg: AppConfig) -> None:
    mock_cfg.email.enabled = True
    mock_cfg.email.recipients = ["test@example.com"]
    mock_send.side_effect = ValueError("Bad email config")
    res = _finalize_pdf_and_optional_email(
        cfg=mock_cfg,
        output=Path("test.pdf"),
        period_start="2026-04-01",
        period_end="2026-04-01",
        zone_keys=["z1"],
        send_email=True,
        pdf_written_line="Wrote test.pdf",
    )
    assert res.exit_code == exits.INVALID_PARAMS
    assert "Bad email config" in res.stderr


@patch("cloudflare_executive_report.report.command_flow.pdf_report_period_for_options")
@patch("cloudflare_executive_report.report.command_flow.load_report_json")
@patch("cloudflare_executive_report.report.command_flow.is_report_snapshot_valid")
@patch("cloudflare_executive_report.report.command_flow.data_fingerprint_matches")
def test_run_report_pdf_command_cache_only_no_snapshot(
    mock_fingerprint_matches: MagicMock,
    mock_snapshot_valid: MagicMock,
    mock_load_json: MagicMock,
    mock_period: MagicMock,
    mock_cfg: AppConfig,
) -> None:
    mock_period.return_value = ("2026-04-01", "2026-04-01")
    mock_load_json.return_value = None
    mock_snapshot_valid.return_value = False

    sync_opts = SyncOptions(mode=SyncMode.last_n, last_n=1)

    res = run_report_pdf_command(
        cfg=mock_cfg,
        sync_opts=sync_opts,
        output=Path("out.pdf"),
        zone_effective=None,
        zone_keys=["z1"],
        scoped_zone_ids=["z1"],
        pdf_streams=("http",),
        top=5,
        type_set=frozenset(["http"]),
        include_today=False,
        cache_only=True,  # Important
        refresh_health=False,
    )

    assert res.exit_code == exits.INVALID_PARAMS
    assert "No matching report snapshot" in res.stderr
