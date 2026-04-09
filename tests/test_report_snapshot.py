"""Tests for on-disk report JSON snapshot validation."""

from __future__ import annotations

from typing import Any

import pytest

from cloudflare_executive_report.common.report_snapshot import (
    data_fingerprint_matches,
    is_report_snapshot_valid,
)


def _minimal_valid_report() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "partial": False,
        "missing_days": [],
        "report_period": {"start": "2026-01-01", "end": "2026-01-07"},
        "report_type": "last_7",
        "data_fingerprint": {
            "start": "2026-01-01",
            "end": "2026-01-07",
            "zones": ["z1"],
            "top": 10,
            "types": ["dns"],
            "include_today": False,
        },
        "zone_health_fetched_at": "2026-01-08T12:00:00Z",
        "generated_at": "2026-01-08T12:00:00Z",
        "tool_version": "0.1.0",
        "zones": [{"zone_id": "z1", "zone_name": "example.com"}],
    }


@pytest.mark.parametrize(
    "broken",
    [
        None,
        {},
        {"schema_version": 2},
        {"schema_version": 1, "partial": "no"},
        {"schema_version": 1, "partial": False, "missing_days": [1]},
        {"schema_version": 1, "partial": False, "missing_days": [], "report_period": {}},
        {
            "schema_version": 1,
            "partial": False,
            "missing_days": [],
            "report_period": {"start": "", "end": "x"},
        },
    ],
)
def test_is_report_snapshot_valid_rejects_invalid(broken: dict[str, Any] | None) -> None:
    assert is_report_snapshot_valid(broken) is False


def test_is_report_snapshot_valid_accepts_minimal() -> None:
    assert is_report_snapshot_valid(_minimal_valid_report()) is True


def test_data_fingerprint_matches() -> None:
    rep = _minimal_valid_report()
    fp = rep["data_fingerprint"]
    assert isinstance(fp, dict)
    assert data_fingerprint_matches(rep, dict(fp)) is True
    assert data_fingerprint_matches(rep, {**fp, "top": 99}) is False
    assert data_fingerprint_matches(None, fp) is False
