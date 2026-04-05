"""Tests for PDF cache loaders."""

from __future__ import annotations

from pathlib import Path

import pytest

from cloudflare_executive_report.pdf.loader import load_dns_for_range, load_http_for_range

FIXTURE_CACHE = Path(__file__).resolve().parent.parent / "docs" / "sample-data" / "cache"
ZONE_ID = "a1b2c3d4e5f6789012345678abcdef01"


@pytest.mark.skipif(not FIXTURE_CACHE.is_dir(), reason="sample cache fixtures missing")
def test_load_dns_single_day() -> None:
    r = load_dns_for_range(
        FIXTURE_CACHE,
        ZONE_ID,
        "example.com",
        "2026-04-01",
        "2026-04-01",
        top=5,
    )
    assert r.api_day_count == 1
    assert int(r.rollup.get("total_queries") or 0) == 125000
    assert len(r.daily_queries) == 1
    assert r.daily_queries[0][1] == 125000


@pytest.mark.skipif(not FIXTURE_CACHE.is_dir(), reason="sample cache fixtures missing")
def test_load_http_single_day() -> None:
    r = load_http_for_range(
        FIXTURE_CACHE,
        ZONE_ID,
        "example.com",
        "2026-04-01",
        "2026-04-01",
        top=5,
    )
    assert r.api_day_count == 1
    assert int(r.rollup.get("total_requests") or 0) == 45200
    assert len(r.daily_requests) == 1


@pytest.mark.skipif(not FIXTURE_CACHE.is_dir(), reason="sample cache fixtures missing")
def test_load_dns_missing_days_tracked() -> None:
    r = load_dns_for_range(
        FIXTURE_CACHE,
        ZONE_ID,
        "example.com",
        "2026-04-01",
        "2026-04-03",
        top=5,
    )
    assert len(r.daily_queries) == 3
    assert r.daily_queries[0][1] == 125000
    assert r.daily_queries[1][1] is None
    assert r.daily_queries[2][1] is None
    assert "2026-04-02" in r.missing_dates
    assert "2026-04-03" in r.missing_dates
