"""Matplotlib time-series figures (non-interactive backend)."""

from __future__ import annotations

import io
from collections.abc import Sequence
from datetime import date

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from cloudflare_executive_report.pdf.theme import Theme


def aggregate_values_for_chart(
    points: Sequence[tuple[date, int | None]],
) -> tuple[list[date], list[float | None], str]:
    """
    Reduce point count for long ranges. Returns (dates, values with None gaps, subtitle).
    """
    raw_dates = [d for d, _ in points]
    raw_vals = [v for _, v in points]
    n = len(points)
    if n == 0:
        return [], [], ""

    def daily() -> tuple[list[date], list[float | None], str]:
        return raw_dates, [float(v) if v is not None else None for v in raw_vals], ""

    if n <= 7:
        return daily()
    if n <= 60:
        return daily()
    if n <= 365:
        return _bucket_weekly(points, "Weekly totals (sum per 7-day bucket)")

    dates, vals, _ = _bucket_monthly(points, "")
    if len(dates) > 24:
        dates = dates[-24:]
        vals = vals[-24:]
        return dates, vals, "Monthly totals - last 24 months shown"
    return dates, vals, "Monthly totals (sum per calendar month)"


def _bucket_weekly(
    points: Sequence[tuple[date, int | None]],
    subtitle: str,
) -> tuple[list[date], list[float | None], str]:
    chunks: list[list[tuple[date, int | None]]] = []
    cur: list[tuple[date, int | None]] = []
    for p in points:
        cur.append(p)
        if len(cur) >= 7:
            chunks.append(cur)
            cur = []
    if cur:
        chunks.append(cur)
    out_dates: list[date] = []
    out_vals: list[float | None] = []
    for ch in chunks:
        d0 = ch[0][0]
        vs = [x[1] for x in ch]
        if all(x is None for x in vs):
            out_vals.append(None)
        else:
            out_vals.append(float(sum(x for x in vs if x is not None)))
        out_dates.append(d0)
    return out_dates, out_vals, subtitle


def _bucket_monthly(
    points: Sequence[tuple[date, int | None]],
    subtitle: str,
) -> tuple[list[date], list[float | None], str]:
    buckets: dict[tuple[int, int], list[int | None]] = {}
    order: list[tuple[int, int]] = []
    for d, v in points:
        key = (d.year, d.month)
        if key not in buckets:
            buckets[key] = []
            order.append(key)
        buckets[key].append(v)
    out_dates: list[date] = []
    out_vals: list[float | None] = []
    for key in order:
        vs = buckets[key]
        if all(x is None for x in vs):
            out_vals.append(None)
        else:
            out_vals.append(float(sum(x for x in vs if x is not None)))
        y, m = key
        out_dates.append(date(y, m, 1))
    return out_dates, out_vals, subtitle


def line_chart_bytes(
    dates: Sequence[date],
    values: Sequence[float | None],
    *,
    title: str,
    subtitle: str,
    y_label: str,
    theme: Theme,
) -> bytes:
    """Line chart; None values create gaps (no line through missing)."""
    fig_w = min(theme.content_width_in(), 7.1)
    fig_h = fig_w * 0.35
    fig, ax = plt.subplots(figsize=(fig_w, fig_h), facecolor="white")
    xs = list(range(len(dates)))
    ys: list[float | None] = list(values)
    if not dates:
        ax.text(0.5, 0.5, "No data", ha="center", va="center", color=theme.muted)
    else:
        segments: list[tuple[list[int], list[float]]] = []
        cur_x: list[int] = []
        cur_y: list[float] = []
        for i, y in enumerate(ys):
            if y is None:
                if cur_x:
                    segments.append((cur_x, cur_y))
                    cur_x, cur_y = [], []
                continue
            cur_x.append(i)
            cur_y.append(y)
        if cur_x:
            segments.append((cur_x, cur_y))
        for cx, cy in segments:
            ax.plot(cx, cy, color=theme.primary, linewidth=2.0, marker="o", markersize=3)
        ax.set_xticks(xs)
        fmt = "%Y-%m-%d" if len(dates) <= 14 else "%m/%d"
        labels = [d.strftime(fmt) for d in dates]
        ax.set_xticklabels(labels, rotation=35, ha="right", fontsize=7, color=theme.muted)
        ax.set_ylabel(y_label, fontsize=8, color=theme.muted)
        ax.grid(axis="y", linestyle="--", alpha=0.35)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
    ax.set_title(title, fontsize=10, color=theme.slate, pad=8)
    if subtitle:
        fig.text(0.5, 0.02, subtitle, ha="center", fontsize=7, color=theme.muted)
    buf = io.BytesIO()
    fig.savefig(
        buf,
        format="png",
        dpi=theme.chart_dpi,
        bbox_inches="tight",
        facecolor="white",
        pad_inches=0.15,
    )
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def prepare_daily_metric_series(
    points: Sequence[tuple[date, int | None]],
    theme: Theme,
    *,
    chart_title: str,
    y_axis_label: str,
) -> tuple[bytes, str]:
    """
    Build a time-series PNG from per-day values (None = gap).

    Any stream can call this with its own ``chart_title`` and ``y_axis_label``.
    """
    d, v, sub = aggregate_values_for_chart(points)
    if len(d) < 2:
        return b"", sub
    png = line_chart_bytes(
        d,
        v,
        title=chart_title,
        subtitle=sub,
        y_label=y_axis_label,
        theme=theme,
    )
    return png, sub
