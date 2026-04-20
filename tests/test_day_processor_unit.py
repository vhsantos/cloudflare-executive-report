"""Unit tests for sync/day_processor.py."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

from cloudflare_executive_report.sync.day_processor import process_day, should_refetch_cached


def test_should_refetch_cached() -> None:
    assert should_refetch_cached(None, False) is True
    assert should_refetch_cached(None, True) is True
    assert should_refetch_cached({"_source": "api"}, False) is False
    assert should_refetch_cached({"_source": "api"}, True) is True
    assert should_refetch_cached({"_source": "error"}, False) is True
    assert should_refetch_cached({"_source": "null"}, False) is False


@patch("cloudflare_executive_report.sync.day_processor.read_day_file")
@patch("cloudflare_executive_report.sync.day_processor.write_day_file")
@patch("cloudflare_executive_report.sync.day_processor.day_cache_path")
def test_process_day_success(
    mock_path: MagicMock,
    mock_write: MagicMock,
    mock_read: MagicMock,
    tmp_path: Path,
) -> None:
    fetcher = MagicMock()
    fetcher.stream_id = "http"
    fetcher.outside_retention.return_value = False
    fetcher.fetch.return_value = {"data": 1}

    mock_read.return_value = None
    mock_path.return_value = tmp_path / "day.json"

    client = MagicMock()

    res = process_day(
        fetcher,
        client,
        tmp_path,
        "z1",
        "n1",
        date(2026, 4, 1),
        plan_legacy_id="pro",
        zone_meta={},
        force_fetch=False,
        refresh=False,
    )

    assert res is False
    assert mock_write.called
    assert fetcher.fetch.called


@patch("cloudflare_executive_report.sync.day_processor.read_day_file")
@patch("cloudflare_executive_report.sync.day_processor.write_day_file")
@patch("cloudflare_executive_report.sync.day_processor.day_cache_path")
def test_process_day_outside_retention(
    mock_path: MagicMock,
    mock_write: MagicMock,
    mock_read: MagicMock,
    tmp_path: Path,
) -> None:
    fetcher = MagicMock()
    fetcher.stream_id = "http"
    fetcher.outside_retention.return_value = True

    mock_path.return_value = tmp_path / "day.json"

    client = MagicMock()

    res = process_day(
        fetcher,
        client,
        tmp_path,
        "z1",
        "n1",
        date(2020, 1, 1),
        plan_legacy_id="pro",
        zone_meta={},
        force_fetch=False,
        refresh=False,
    )

    assert res is False
    mock_write.assert_called_with(mock_path.return_value, source="null", data=None)
