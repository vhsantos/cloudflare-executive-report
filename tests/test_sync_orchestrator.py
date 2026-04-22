"""Unit tests for sync/orchestrator.py."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

from cloudflare_executive_report import exits
from cloudflare_executive_report.cache import CacheLockTimeout, ZoneIndex
from cloudflare_executive_report.config import AppConfig, ZoneEntry
from cloudflare_executive_report.sync.options import SyncMode, SyncOptions
from cloudflare_executive_report.sync.orchestrator import (
    _dates_incremental,
    _sync_days_for_mode,
    run_sync,
)


def test_dates_incremental() -> None:
    y = date(2026, 4, 15)
    # 1. No latest index (defaults to yesterday)
    assert _dates_incremental(None, y) == []

    # 2. Latest is same as yesterday
    assert _dates_incremental("2026-04-15", y) == []

    # 3. Latest is 2 days ago
    assert _dates_incremental("2026-04-13", y) == [date(2026, 4, 14), date(2026, 4, 15)]


def test_sync_days_for_mode_last_n() -> None:
    opts = SyncOptions(mode=SyncMode.last_n, last_n=2)
    y = date(2026, 4, 15)
    days = _sync_days_for_mode(opts, {}, y)
    assert days == [date(2026, 4, 14), date(2026, 4, 15)]


def test_sync_days_for_mode_range() -> None:
    opts = SyncOptions(mode=SyncMode.range, start="2026-04-10", end="2026-04-12")
    y = date(2026, 4, 15)
    days = _sync_days_for_mode(opts, {}, y)
    assert days == [date(2026, 4, 10), date(2026, 4, 11), date(2026, 4, 12)]


def test_run_sync_lock_timeout(tmp_path: Path) -> None:
    cfg = AppConfig(api_token="x", cache_dir=str(tmp_path), zones=[ZoneEntry(id="z1", name="n1")])
    opts = SyncOptions(mode=SyncMode.incremental)

    with patch("cloudflare_executive_report.sync.orchestrator.cache_lock") as mock_lock:
        mock_lock.side_effect = CacheLockTimeout("Locked")
        res = run_sync(cfg, opts)
        assert res == exits.CACHE_LOCK_TIMEOUT


@patch("cloudflare_executive_report.sync.orchestrator.CloudflareClient")
@patch("cloudflare_executive_report.sync.orchestrator.cache_lock")
@patch("cloudflare_executive_report.sync.orchestrator.load_zone_index")
def test_run_sync_auth_failure(
    mock_load_idx: MagicMock,
    mock_lock: MagicMock,
    mock_client_cls: MagicMock,
    tmp_path: Path,
) -> None:
    cfg = AppConfig(api_token="x", cache_dir=str(tmp_path), zones=[ZoneEntry(id="z1", name="n1")])
    opts = SyncOptions(mode=SyncMode.incremental)

    client = mock_client_cls.return_value.__enter__.return_value
    from cloudflare_executive_report.cf_client import CloudflareAuthError

    client.get_zone.side_effect = CloudflareAuthError("Invalid token")

    res = run_sync(cfg, opts)
    assert res == exits.AUTH_FAILED


@patch("cloudflare_executive_report.sync.orchestrator.CloudflareClient")
@patch("cloudflare_executive_report.sync.orchestrator.cache_lock")
@patch("cloudflare_executive_report.sync.orchestrator.load_zone_index")
@patch("cloudflare_executive_report.sync.orchestrator.process_day")
@patch("cloudflare_executive_report.sync.orchestrator.save_zone_index")
def test_run_sync_success_flow(
    mock_save_idx: MagicMock,
    mock_proc: MagicMock,
    mock_load_idx: MagicMock,
    mock_lock: MagicMock,
    mock_client_cls: MagicMock,
    tmp_path: Path,
) -> None:
    cfg = AppConfig(api_token="x", cache_dir=str(tmp_path), zones=[ZoneEntry(id="z1", name="n1")])
    opts = SyncOptions(mode=SyncMode.last_n, last_n=1, types=["http"])

    client = mock_client_cls.return_value.__enter__.return_value
    client.get_zone.return_value = {"id": "z1", "plan": {"legacy_id": "pro"}}

    mock_load_idx.return_value = ZoneIndex(zone_id="z1", zone_name="n1")
    mock_proc.return_value = False  # No rate limit

    # We also need to mock build_report etc if write_report_json=True
    with patch("cloudflare_executive_report.sync.orchestrator.build_report") as mock_build:
        mock_build.return_value = {"zones": []}
        res = run_sync(cfg, opts, write_report_json=True)
        assert res == exits.SUCCESS

    assert mock_proc.called
    assert mock_save_idx.called


def test_run_sync_zone_not_found(tmp_path: Path) -> None:
    cfg = AppConfig(api_token="x", cache_dir=str(tmp_path), zones=[ZoneEntry(id="z1", name="n1")])
    opts = SyncOptions(mode=SyncMode.incremental)
    res = run_sync(cfg, opts, zone_filter="non-existent")
    assert res == exits.INVALID_PARAMS


def test_run_sync_no_zones(tmp_path: Path) -> None:
    cfg = AppConfig(api_token="x", cache_dir=str(tmp_path), zones=[])
    opts = SyncOptions(mode=SyncMode.incremental)
    res = run_sync(cfg, opts)
    assert res == exits.INVALID_PARAMS


def test_run_sync_range_end_too_late(tmp_path: Path) -> None:
    cfg = AppConfig(api_token="x", cache_dir=str(tmp_path), zones=[ZoneEntry(id="z1", name="n1")])
    # Future date
    opts = SyncOptions(mode=SyncMode.range, start="2026-01-01", end="2099-01-01")

    with (
        patch("cloudflare_executive_report.sync.orchestrator.cache_lock"),
        patch("cloudflare_executive_report.sync.orchestrator.CloudflareClient"),
    ):
        res = run_sync(cfg, opts)
        assert res == exits.INVALID_PARAMS


@patch("cloudflare_executive_report.sync.orchestrator.CloudflareClient")
@patch("cloudflare_executive_report.sync.orchestrator.cache_lock")
def test_run_sync_api_error_lookup(
    mock_lock: MagicMock,
    mock_client_cls: MagicMock,
    tmp_path: Path,
) -> None:
    cfg = AppConfig(api_token="x", cache_dir=str(tmp_path), zones=[ZoneEntry(id="z1", name="n1")])
    opts = SyncOptions(mode=SyncMode.incremental)

    client = mock_client_cls.return_value.__enter__.return_value
    from cloudflare_executive_report.cf_client import CloudflareAPIError

    client.get_zone.side_effect = CloudflareAPIError("API error")

    res = run_sync(cfg, opts)
    assert res == exits.GENERAL_ERROR
