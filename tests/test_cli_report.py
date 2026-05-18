"""Unit tests for the CLI 'report' command overrides."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from cloudflare_executive_report import exits
from cloudflare_executive_report.cli import app
from cloudflare_executive_report.config import AppConfig, ZoneEntry


@pytest.fixture
def mock_cfg_with_zone() -> AppConfig:
    """Return a baseline config with one configured zone for report generation."""
    return AppConfig(
        api_token="valid_token_value",
        zones=[ZoneEntry(id="z123", name="example.com")],
    )


@patch("cloudflare_executive_report.cli.cache_has_any_zone_data")
@patch("cloudflare_executive_report.cli.run_report_pdf_command")
def test_cli_report_profile_override_valid(
    mock_run_cmd: MagicMock,
    mock_cache_has_data: MagicMock,
    mock_cfg_with_zone: AppConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that valid profile overrides via CLI are correctly set in the config."""
    monkeypatch.setattr(
        "cloudflare_executive_report.cli.load_app_config",
        lambda *args, **kwargs: mock_cfg_with_zone,
    )
    monkeypatch.setattr(
        "cloudflare_executive_report.cli.setup_logging",
        lambda **kwargs: None,
    )

    mock_cache_has_data.return_value = True
    mock_run_cmd.return_value = MagicMock(exit_code=exits.SUCCESS, ai_summary=None)

    runner = CliRunner()
    result = runner.invoke(
        app,
        ["report", "-o", "out.pdf", "--profile", "minimal", "--cache-only"],
    )

    assert result.exit_code == exits.SUCCESS
    mock_run_cmd.assert_called_once()
    passed_cfg = mock_run_cmd.call_args[1]["cfg"]
    assert passed_cfg.pdf.profile == "minimal"


@patch("cloudflare_executive_report.cli.run_report_pdf_command")
def test_cli_report_profile_override_invalid(
    mock_run_cmd: MagicMock,
    mock_cfg_with_zone: AppConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that invalid profile overrides via CLI raise error and abort."""
    monkeypatch.setattr(
        "cloudflare_executive_report.cli.load_app_config",
        lambda *args, **kwargs: mock_cfg_with_zone,
    )
    monkeypatch.setattr(
        "cloudflare_executive_report.cli.setup_logging",
        lambda **kwargs: None,
    )

    runner = CliRunner()
    result = runner.invoke(
        app,
        ["report", "-o", "out.pdf", "--profile", "super_detailed", "--cache-only"],
    )

    assert result.exit_code == exits.INVALID_PARAMS
    assert "must be minimal, executive, or detailed" in result.output
    mock_run_cmd.assert_not_called()
