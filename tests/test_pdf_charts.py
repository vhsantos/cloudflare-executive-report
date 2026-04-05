"""Chart builders (matplotlib Agg)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

pytest.importorskip("matplotlib")

from cloudflare_executive_report.pdf.charts import (
    aggregate_stacked_pairs_for_chart,
    prepare_daily_metric_series,
    prepare_stacked_daily_metric_series,
)
from cloudflare_executive_report.pdf.theme import DEFAULT_THEME


def test_prepare_stacked_daily_metric_series_bytes_scale() -> None:
    pts = [
        (date(2026, 4, 1), (100 * 1024 * 1024, 50 * 1024 * 1024)),
        (date(2026, 4, 2), (110 * 1024 * 1024, 60 * 1024 * 1024)),
        (date(2026, 4, 3), (90 * 1024 * 1024, 70 * 1024 * 1024)),
    ]
    png, _sub = prepare_stacked_daily_metric_series(
        pts,
        DEFAULT_THEME,
        chart_title="BW",
        bottom_legend="Cached",
        top_legend="Uncached",
        y_scale="bytes",
    )
    assert len(png) > 500


def test_prepare_stacked_daily_metric_series_non_empty() -> None:
    pts = [
        (date(2026, 4, 1), (10, 90)),
        (date(2026, 4, 2), (20, 80)),
        (date(2026, 4, 3), (15, 85)),
    ]
    png, _sub = prepare_stacked_daily_metric_series(
        pts,
        DEFAULT_THEME,
        chart_title="Test",
        bottom_legend="Cached",
        top_legend="Uncached",
    )
    assert len(png) > 500


def test_prepare_daily_metric_series_non_empty() -> None:
    pts = [(date(2026, 4, d), d * 100) for d in range(1, 5)]
    png, _ = prepare_daily_metric_series(
        pts,
        DEFAULT_THEME,
        chart_title="Uniques",
        y_axis_label="UV",
    )
    assert len(png) > 500


def test_aggregate_stacked_pairs_weekly_bucket() -> None:
    d0 = date(2026, 1, 1)
    pts = [(d0 + timedelta(days=i), (1, 2)) for i in range(61)]
    d, pairs, _sub, gran = aggregate_stacked_pairs_for_chart(pts)
    assert gran == "week"
    assert len(d) < len(pts)
    assert all(p[0] is not None and p[1] is not None for p in pairs)
