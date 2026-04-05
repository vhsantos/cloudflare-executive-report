"""Matplotlib time-series figures (non-interactive backend)."""

from __future__ import annotations

import calendar
import io
from collections.abc import Sequence
from datetime import date
from typing import Literal

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import ticker
from matplotlib.colors import to_rgba
from matplotlib.patches import Patch

from cloudflare_executive_report.pdf.theme import Theme

ChartTimeGranularity = Literal["day", "week", "month"]


def aggregate_values_for_chart(
    points: Sequence[tuple[date, int | None]],
) -> tuple[list[date], list[float | None], str, ChartTimeGranularity]:
    """
    Reduce point count for long ranges.

    Returns (dates, values with None gaps, subtitle, time granularity for x-axis labels).
    """
    raw_dates = [d for d, _ in points]
    raw_vals = [v for _, v in points]
    n = len(points)
    if n == 0:
        return [], [], "", "day"

    def daily() -> tuple[list[date], list[float | None], str, ChartTimeGranularity]:
        return raw_dates, [float(v) if v is not None else None for v in raw_vals], "", "day"

    if n <= 7:
        return daily()
    if n <= 60:
        return daily()
    if n <= 365:
        d, v, s = _bucket_weekly(points, "Weekly totals (sum per 7-day bucket)")
        return d, v, s, "week"

    dates, vals, _ = _bucket_monthly(points, "")
    if len(dates) > 24:
        dates = dates[-24:]
        vals = vals[-24:]
        return dates, vals, "Monthly totals - last 24 months shown", "month"
    return dates, vals, "Monthly totals (sum per calendar month)", "month"


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


def _format_y_tick_cf(value: float, _pos: int | None = None) -> str:
    """Compact Y ticks like Cloudflare analytics (0, 5k, 10k, 25.74k)."""
    if value == 0:
        return "0"
    x = float(value)
    axv = abs(x)
    if axv >= 1_000_000_000:
        v = x / 1_000_000_000.0
        s = f"{v:.2f}".rstrip("0").rstrip(".")
        return f"{s}B"
    if axv >= 1_000_000:
        v = x / 1_000_000.0
        s = f"{v:.2f}".rstrip("0").rstrip(".")
        return f"{s}M"
    if axv >= 1000:
        v = x / 1000.0
        s = f"{v:.2f}".rstrip("0").rstrip(".")
        return f"{s}k"
    if x == int(x):
        return str(int(x))
    return f"{x:.1f}".rstrip("0").rstrip(".")


def _x_axis_labels_cf(
    dates: Sequence[date],
    granularity: ChartTimeGranularity,
) -> list[str]:
    """
    X tick text: one style per granularity (no mixing).

    - ``month``: month labels only: ``Apr`` or ``Apr '25`` if the range spans years.
    - ``day`` / ``week``: weekday + day of month for every point: ``Tue 31``, ``Wed 01``, …
    """
    if not dates:
        return []
    if granularity == "month":
        y0, y1 = dates[0].year, dates[-1].year
        multi_year = y0 != y1
        return [d.strftime("%b '%y") if multi_year else d.strftime("%b") for d in dates]

    # Daily or weekly buckets: always DoW + day (including across month boundaries).
    return [f"{calendar.day_abbr[d.weekday()]} {d.day:02d}" for d in dates]


def _xtick_indices(n: int, max_labels: int = 11) -> list[int]:
    """Sparse tick indices so labels do not crowd the axis."""
    if n <= 0:
        return []
    if n <= max_labels:
        return list(range(n))
    step = max(1, (n - 1) // (max_labels - 1))
    idx = list(range(0, n, step))
    if idx[-1] != n - 1:
        idx.append(n - 1)
    return sorted(set(idx))


def line_chart_bytes(
    dates: Sequence[date],
    values: Sequence[float | None],
    *,
    title: str,
    subtitle: str,
    y_label: str,
    theme: Theme,
    time_granularity: ChartTimeGranularity = "day",
) -> bytes:
    """Stacked-area style (single series): filled region + top edge; compact Y and X ticks."""
    fig_w = min(theme.content_width_in(), 7.1)
    fig_h = fig_w * 0.35
    fig, ax = plt.subplots(figsize=(fig_w, fig_h), facecolor="white")
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

        line_c = theme.primary
        fill_c = to_rgba(line_c, 0.22)
        for cx, cy in segments:
            ax.fill_between(cx, 0, cy, color=fill_c, linewidth=0, interpolate=True)
            ax.plot(cx, cy, color=line_c, linewidth=1.4, solid_capstyle="round")

        tick_idx = _xtick_indices(len(dates))
        full_labels = _x_axis_labels_cf(dates, time_granularity)
        ax.set_xticks(tick_idx)
        ax.set_xticklabels(
            [full_labels[i] for i in tick_idx],
            rotation=0,
            ha="center",
            fontsize=7,
            color=theme.muted,
        )
        ax.yaxis.set_major_formatter(ticker.FuncFormatter(_format_y_tick_cf))
        ax.tick_params(axis="y", labelsize=7, colors=theme.muted)
        ax.grid(axis="both", linestyle="-", alpha=0.2, color=theme.border)
        ax.set_axisbelow(True)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

        if segments:
            leg_handle = Patch(facecolor=fill_c, edgecolor=line_c, linewidth=1.0, label=y_label)
            ax.legend(
                handles=[leg_handle],
                loc="upper right",
                frameon=False,
                fontsize=7,
                handlelength=1.1,
                handletextpad=0.45,
                borderaxespad=0.5,
            )
            leg = ax.get_legend()
            if leg is not None:
                for text in leg.get_texts():
                    text.set_color(theme.slate)
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
    d, v, sub, gran = aggregate_values_for_chart(points)
    if len(d) < 2:
        return b"", sub
    png = line_chart_bytes(
        d,
        v,
        title=chart_title,
        subtitle=sub,
        y_label=y_axis_label,
        theme=theme,
        time_granularity=gran,
    )
    return png, sub
