from __future__ import annotations

from datetime import date

from cloudflare_executive_report.common.period_resolver import (
    build_data_fingerprint,
    normalize_report_type,
    report_type_for_options,
    resolved_period_for_options,
    semantic_baseline_bounds,
)
from cloudflare_executive_report.sync.options import SyncMode, SyncOptions


def test_report_type_for_options():
    assert (
        report_type_for_options(
            SyncOptions(mode=SyncMode.range, start="2026-01-01", end="2026-01-02")
        )
        == "custom"
    )
    assert report_type_for_options(SyncOptions(mode=SyncMode.incremental)) == "incremental"
    assert report_type_for_options(SyncOptions(mode=SyncMode.last_n, last_n=7)) == "last_7"
    assert report_type_for_options(SyncOptions(mode=SyncMode.last_month)) == "last_month"


def test_resolved_period_for_last_n():
    start, end = resolved_period_for_options(
        opts=SyncOptions(mode=SyncMode.last_n, last_n=2),
        y=date(2026, 4, 9),
        today=date(2026, 4, 10),
    ) or (None, None)
    assert start == date(2026, 4, 8)
    assert end == date(2026, 4, 9)


def test_semantic_baseline_this_month_is_capped():
    start, end = semantic_baseline_bounds(
        report_type="this_month",
        y=date(2026, 4, 30),
        today=date(2026, 3, 31),
    ) or (None, None)
    assert start == date(2026, 2, 1)
    assert end == date(2026, 2, 28)


def test_normalize_report_type():
    assert normalize_report_type("last_month") == "last_month"
    assert normalize_report_type("last_30") == "last_30"
    assert normalize_report_type("unknown_type") is None


def test_data_fingerprint_is_canonical():
    fp = build_data_fingerprint(
        start="2026-04-01",
        end="2026-04-30",
        zones=["z2", "z1", "z1"],
        top=10,
        types={"HTTP", "dns"},
        include_today=False,
    )
    assert fp["zones"] == ["z1", "z2"]
    assert fp["types"] == ["dns", "http"]
