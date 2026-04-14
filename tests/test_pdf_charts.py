"""Chart builders (matplotlib Agg)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

pytest.importorskip("matplotlib")

from cloudflare_executive_report.pdf.charts import (
    aggregate_dual_series_for_chart,
    prepare_dual_line_daily_series,
    prepare_single_line_daily_series,
    prepare_triple_line_daily_series,
)
from cloudflare_executive_report.pdf.theme import DEFAULT_THEME


def test_prepare_single_line_daily_series_non_empty() -> None:
    pts = [(date(2026, 4, d), d * 100) for d in range(1, 5)]
    png, _ = prepare_single_line_daily_series(
        pts,
        DEFAULT_THEME,
        chart_title="Uniques",
        y_axis_label="UV",
    )
    assert len(png) > 500


def test_prepare_dual_line_daily_series_non_empty() -> None:
    pts = [
        (date(2026, 4, 1), (300, 700)),
        (date(2026, 4, 2), (310, 690)),
        (date(2026, 4, 3), (290, 710)),
    ]
    png, _sub = prepare_dual_line_daily_series(
        pts,
        DEFAULT_THEME,
        chart_title="CF vs origin",
        legend_a="Cloudflare",
        legend_b="Origin",
    )
    assert len(png) > 500


def test_prepare_triple_line_daily_series_non_empty() -> None:
    pts = [
        (date(2026, 4, 1), (100, 200, 700)),
        (date(2026, 4, 2), (110, 190, 700)),
        (date(2026, 4, 3), (90, 210, 700)),
    ]
    png, _sub = prepare_triple_line_daily_series(
        pts,
        DEFAULT_THEME,
        chart_title="Triple lines",
        legend_a="CF",
        legend_b="Origin",
        legend_c="Mitigated",
    )
    assert len(png) > 500


def test_aggregate_stacked_pairs_weekly_bucket() -> None:
    d0 = date(2026, 1, 1)
    pts = [(d0 + timedelta(days=i), (1, 2)) for i in range(61)]
    d, pairs, _sub, gran = aggregate_dual_series_for_chart(pts)
    assert gran == "week"
    assert len(d) < len(pts)
    assert all(p[0] is not None and p[1] is not None for p in pairs)
