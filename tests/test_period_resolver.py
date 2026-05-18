from __future__ import annotations

from datetime import date

from cloudflare_executive_report.common.period_resolver import (
    build_data_fingerprint,
    normalize_report_type,
    report_type_for_options,
    resolved_period_for_options,
    semantic_baseline_bounds,
    semantic_current_bounds,
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
        top=10,
        types={"HTTP", "dns"},
        include_today=False,
    )
    assert fp["types"] == ["dns", "http"]


def test_semantic_bounds_fixes_monday_first_day():
    # Test last_week on Monday (first day of new week)
    # y (yesterday) = Sun May 17, today = Mon May 18.
    # Expect last_week to be May 11 - May 17 (the completed week).
    sw, ew = semantic_current_bounds(
        report_type="last_week",
        y=date(2026, 5, 17),
        today=date(2026, 5, 18),
    ) or (None, None)
    assert sw == date(2026, 5, 11)
    assert ew == date(2026, 5, 17)

    # Test last_week on Sunday (last day of current week)
    # y = Sat May 16, today = Sun May 17.
    # Expect last_week to be May 4 - May 10 (since May 11 - May 17 is still in progress).
    sw, ew = semantic_current_bounds(
        report_type="last_week",
        y=date(2026, 5, 16),
        today=date(2026, 5, 17),
    ) or (None, None)
    assert sw == date(2026, 5, 4)
    assert ew == date(2026, 5, 10)

    # Test last_week on Tuesday
    # y = Mon May 18, today = Tue May 19.
    # Expect last_week to be May 11 - May 17.
    sw, ew = semantic_current_bounds(
        report_type="last_week",
        y=date(2026, 5, 18),
        today=date(2026, 5, 19),
    ) or (None, None)
    assert sw == date(2026, 5, 11)
    assert ew == date(2026, 5, 17)

    # Test last_month on first day of month
    # y = May 31, today = June 1.
    # Expect last_month to be May 1 - May 31 (fully completed month).
    sm, em = semantic_current_bounds(
        report_type="last_month",
        y=date(2026, 5, 31),
        today=date(2026, 6, 1),
    ) or (None, None)
    assert sm == date(2026, 5, 1)
    assert em == date(2026, 5, 31)

    # Test last_month on last day of month
    # y = May 30, today = May 31.
    # Expect last_month to be April 1 - April 30 (since May is still in progress).
    sm, em = semantic_current_bounds(
        report_type="last_month",
        y=date(2026, 5, 30),
        today=date(2026, 5, 31),
    ) or (None, None)
    assert sm == date(2026, 4, 1)
    assert em == date(2026, 4, 30)

    # Test last_year on Jan 1st
    # y = Dec 31, 2025, today = Jan 1, 2026.
    # Expect last_year to be Jan 1, 2025 - Dec 31, 2025 (fully completed year).
    sy, ey = semantic_current_bounds(
        report_type="last_year",
        y=date(2025, 12, 31),
        today=date(2026, 1, 1),
    ) or (None, None)
    assert sy == date(2025, 1, 1)
    assert ey == date(2025, 12, 31)

    # Test last_year baseline on Jan 1st
    # y = Dec 31, 2025, today = Jan 1, 2026.
    # Expect last_year baseline to be Jan 1, 2024 - Dec 31, 2024.
    sy, ey = semantic_baseline_bounds(
        report_type="last_year",
        y=date(2025, 12, 31),
        today=date(2026, 1, 1),
    ) or (None, None)
    assert sy == date(2024, 1, 1)
    assert ey == date(2024, 12, 31)
