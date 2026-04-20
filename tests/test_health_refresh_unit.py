"""Unit tests for report/health_refresh.py."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cloudflare_executive_report import exits
from cloudflare_executive_report.config import AppConfig, ZoneEntry
from cloudflare_executive_report.report.health_refresh import refresh_snapshot_zone_health
from cloudflare_executive_report.sync.options import SyncMode, SyncOptions


@pytest.fixture
def mock_cfg(tmp_path: Path) -> AppConfig:
    return AppConfig(
        api_token="x",
        cache_dir=str(tmp_path / "cache"),
        output_dir=str(tmp_path / "output"),
        zones=[ZoneEntry(id="z1", name="n1")],
    )


@patch("cloudflare_executive_report.report.health_refresh.load_report_json")
@patch("cloudflare_executive_report.report.health_refresh.is_report_snapshot_valid")
def test_refresh_snapshot_zone_health_missing_snapshot(
    mock_valid: MagicMock,
    mock_load: MagicMock,
    mock_cfg: AppConfig,
) -> None:
    mock_load.return_value = None
    mock_valid.return_value = False
    opts = SyncOptions(mode=SyncMode.incremental)
    res = refresh_snapshot_zone_health(mock_cfg, opts)
    assert res == exits.INVALID_PARAMS


@patch("cloudflare_executive_report.report.health_refresh.load_report_json")
@patch("cloudflare_executive_report.report.health_refresh.is_report_snapshot_valid")
@patch("cloudflare_executive_report.report.health_refresh.CloudflareClient")
@patch(
    "cloudflare_executive_report.report.health_refresh.update_zone_json_block_health_and_executive"
)
@patch("cloudflare_executive_report.report.health_refresh.save_report_json")
def test_refresh_snapshot_zone_health_success(
    mock_save: MagicMock,
    mock_update: MagicMock,
    mock_client_cls: MagicMock,
    mock_valid: MagicMock,
    mock_load: MagicMock,
    mock_cfg: AppConfig,
) -> None:
    mock_load.return_value = {
        "report_period": {"start": "2026-04-01", "end": "2026-04-07"},
        "zones": [{"zone_id": "z1", "zone_name": "n1"}],
        "warnings": [],
    }
    mock_valid.return_value = True

    client = mock_client_cls.return_value.__enter__.return_value
    client.get_zone.return_value = {"id": "z1"}

    mock_update.return_value = []  # warnings

    opts = SyncOptions(mode=SyncMode.incremental)
    res = refresh_snapshot_zone_health(mock_cfg, opts)

    assert res == exits.SUCCESS
    assert mock_save.called
    assert mock_update.called
