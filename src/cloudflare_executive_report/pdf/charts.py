"""Matplotlib time-series figures (non-interactive backend)."""

from __future__ import annotations

import calendar
import io
import math
from collections.abc import Sequence
from datetime import date
from typing import Literal, cast

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import ticker
from matplotlib.colors import to_rgba
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

from cloudflare_executive_report.aggregate import format_bytes_human
from cloudflare_executive_report.pdf.theme import Theme

ChartTimeGranularity = Literal["day", "week", "month"]
ChartYScale = Literal["compact_number", "bytes"]
SecurityTripleStackMode = Literal["absolute", "percent"]

# Bottom + top series for stacked charts (e.g. cached + uncached). ``None`` = missing day.
StackedPoint = tuple[float | None, float | None]
StackedTriplePoint = tuple[float | None, float | None, float | None]


def _sum_aligned_stack_rows(
    rows: Sequence[Sequence[float | None]],
    width: int,
) -> tuple[float | None, ...]:
    """Per-series sums when every row has ``width`` finite values; else all ``None``."""
    acc: list[list[float]] = [[] for _ in range(width)]
    for tup in rows:
        if len(tup) != width:
            continue
        if not all(x is not None for x in tup):
            continue
        for i in range(width):
            acc[i].append(float(tup[i]))  # type: ignore[arg-type]
    if not acc[0]:
        return tuple(None for _ in range(width))
    return tuple(sum(acc[i]) for i in range(width))


def _bucket_weekly_stacked_n(
    points: Sequence[tuple[date, Sequence[float | None]]],
    width: int,
    subtitle: str,
) -> tuple[list[date], list[tuple[float | None, ...]], str]:
    chunks: list[list[tuple[date, Sequence[float | None]]]] = []
    cur: list[tuple[date, Sequence[float | None]]] = []
    for p in points:
        cur.append(p)
        if len(cur) >= 7:
            chunks.append(cur)
            cur = []
    if cur:
        chunks.append(cur)
    out_dates: list[date] = []
    out_vals: list[tuple[float | None, ...]] = []
    for ch in chunks:
        out_dates.append(ch[0][0])
        out_vals.append(_sum_aligned_stack_rows([t for _, t in ch], width))
    return out_dates, out_vals, subtitle


def _bucket_monthly_stacked_n(
    points: Sequence[tuple[date, Sequence[float | None]]],
    width: int,
) -> tuple[list[date], list[tuple[float | None, ...]], str]:
    buckets: dict[tuple[int, int], list[Sequence[float | None]]] = {}
    order: list[tuple[int, int]] = []
    for d, tup in points:
        key = (d.year, d.month)
        if key not in buckets:
            buckets[key] = []
            order.append(key)
        buckets[key].append(tup)
    out_dates: list[date] = []
    out_vals: list[tuple[float | None, ...]] = []
    for key in order:
        y, m = key
        out_dates.append(date(y, m, 1))
        out_vals.append(_sum_aligned_stack_rows(buckets[key], width))
    return out_dates, out_vals, ""


def _aggregate_stacked_for_chart(
    points: Sequence[tuple[date, Sequence[float | None]]],
    width: int,
) -> tuple[list[date], list[tuple[float | None, ...]], str, ChartTimeGranularity]:
    raw_dates = [d for d, _ in points]
    raw_vals = [tuple(t) for _, t in points]
    n = len(points)
    if n == 0:
        return [], [], "", "day"

    def daily() -> tuple[list[date], list[tuple[float | None, ...]], str, ChartTimeGranularity]:
        return raw_dates, raw_vals, "", "day"

    if n <= 7:
        return daily()
    if n <= 60:
        return daily()
    if n <= 365:
        d, v, s = _bucket_weekly_stacked_n(points, width, "Weekly totals (sum per 7-day bucket)")
        return d, v, s, "week"

    dates, vals, _ = _bucket_monthly_stacked_n(points, width)
    if len(dates) > 24:
        dates = dates[-24:]
        vals = vals[-24:]
        return dates, vals, "Monthly totals - last 24 months shown", "month"
    return dates, vals, "Monthly totals (sum per calendar month)", "month"


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


def aggregate_stacked_pairs_for_chart(
    points: Sequence[tuple[date, StackedPoint]],
) -> tuple[list[date], list[StackedPoint], str, ChartTimeGranularity]:
    """Same bucketing rules as ``aggregate_values_for_chart``, for two aligned series."""
    d, v, s, g = _aggregate_stacked_for_chart([(d, p) for d, p in points], 2)
    return d, [cast(StackedPoint, t) for t in v], s, g


def aggregate_triple_stacked_for_chart(
    points: Sequence[tuple[date, StackedTriplePoint]],
) -> tuple[list[date], list[StackedTriplePoint], str, ChartTimeGranularity]:
    """Same bucketing rules as ``aggregate_stacked_pairs_for_chart``, for three aligned series."""
    d, v, s, g = _aggregate_stacked_for_chart([(d, p) for d, p in points], 3)
    return d, [cast(StackedTriplePoint, t) for t in v], s, g


def _format_y_tick_percent(value: float, _pos: int | None = None) -> str:
    if value == int(value):
        return f"{int(value)}%"
    return f"{value:.1f}%"


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


def _format_y_tick_bytes(value: float, _pos: int | None = None) -> str:
    """Y-axis labels for byte totals (KB / MB / GB), not SI millions/billions."""
    if value <= 0:
        return "0B" if value == 0 else ""
    return format_bytes_human(int(max(0, round(value))))


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


def _stacked_segments(
    pairs: Sequence[StackedPoint],
) -> list[tuple[list[int], list[float], list[float]]]:
    """Contiguous index runs where both bottom and top are non-None."""
    segments: list[tuple[list[int], list[float], list[float]]] = []
    cur_x: list[int] = []
    cur_b: list[float] = []
    cur_u: list[float] = []
    for i, (bo, up) in enumerate(pairs):
        if bo is not None and up is not None:
            cur_x.append(i)
            cur_b.append(float(bo))
            cur_u.append(float(up))
            continue
        if cur_x:
            segments.append((cur_x, cur_b, cur_u))
            cur_x, cur_b, cur_u = [], [], []
    if cur_x:
        segments.append((cur_x, cur_b, cur_u))
    return segments


def stacked_area_chart_bytes(
    dates: Sequence[date],
    pairs: Sequence[StackedPoint],
    *,
    title: str,
    subtitle: str,
    bottom_legend: str,
    top_legend: str,
    theme: Theme,
    time_granularity: ChartTimeGranularity = "day",
    y_scale: ChartYScale = "compact_number",
) -> bytes:
    """Stacked areas: bottom series from 0, top series stacked on bottom (CF-style)."""
    fig_w = min(theme.content_width_in(), 7.1)
    fig_h = fig_w * 0.35
    fig, ax = plt.subplots(figsize=(fig_w, fig_h), facecolor="white")
    plist = list(pairs)
    if not dates:
        ax.text(0.5, 0.5, "No data", ha="center", va="center", color=theme.muted)
    else:
        segments = _stacked_segments(plist)
        line_lo = theme.section_blue
        fill_lo = to_rgba(line_lo, 0.42)
        line_hi = theme.primary
        fill_hi = to_rgba(line_hi, 0.2)
        for cx, cb, cu in segments:
            ctop = [cb[i] + cu[i] for i in range(len(cx))]
            ax.fill_between(cx, 0, cb, color=fill_lo, linewidth=0, interpolate=True)
            ax.fill_between(cx, cb, ctop, color=fill_hi, linewidth=0, interpolate=True)
            ax.plot(cx, cb, color=line_lo, linewidth=1.2, solid_capstyle="round")
            ax.plot(cx, ctop, color=line_hi, linewidth=1.4, solid_capstyle="round")

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
        y_fmt = _format_y_tick_bytes if y_scale == "bytes" else _format_y_tick_cf
        ax.yaxis.set_major_formatter(ticker.FuncFormatter(y_fmt))
        ax.tick_params(axis="y", labelsize=7, colors=theme.muted)
        ax.grid(axis="both", linestyle="-", alpha=0.2, color=theme.border)
        ax.set_axisbelow(True)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

        if segments:
            h_lo = Patch(facecolor=fill_lo, edgecolor=line_lo, linewidth=1.0, label=bottom_legend)
            h_hi = Patch(facecolor=fill_hi, edgecolor=line_hi, linewidth=1.0, label=top_legend)
            ax.legend(
                handles=[h_lo, h_hi],
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


def _triple_to_percent_stack(
    mit: list[float],
    srv_cf: list[float],
    srv_or: list[float],
) -> tuple[list[float], list[float], list[float]]:
    """Per-index shares of ``mit + served_cf + served_origin`` summing to 100."""
    out_m: list[float] = []
    out_cf: list[float] = []
    out_or: list[float] = []
    for i in range(len(mit)):
        t = mit[i] + srv_cf[i] + srv_or[i]
        if t <= 0:
            out_m.append(0.0)
            out_cf.append(0.0)
            out_or.append(0.0)
        else:
            out_m.append(100.0 * mit[i] / t)
            out_cf.append(100.0 * srv_cf[i] / t)
            out_or.append(100.0 * srv_or[i] / t)
    return out_m, out_cf, out_or


def _stacked_triple_segments(
    triples: Sequence[StackedTriplePoint],
) -> list[tuple[list[int], list[float], list[float], list[float]]]:
    segments: list[tuple[list[int], list[float], list[float], list[float]]] = []
    cur_x: list[int] = []
    cur_a: list[float] = []
    cur_b: list[float] = []
    cur_c: list[float] = []
    for i, (a, b, c) in enumerate(triples):
        if a is not None and b is not None and c is not None:
            cur_x.append(i)
            cur_a.append(float(a))
            cur_b.append(float(b))
            cur_c.append(float(c))
            continue
        if cur_x:
            segments.append((cur_x, cur_a, cur_b, cur_c))
            cur_x, cur_a, cur_b, cur_c = [], [], [], []
    if cur_x:
        segments.append((cur_x, cur_a, cur_b, cur_c))
    return segments


def stacked_area_chart_triple_bytes(
    dates: Sequence[date],
    triples: Sequence[StackedTriplePoint],
    *,
    title: str,
    subtitle: str,
    legend_bottom: str,
    legend_mid: str,
    legend_top: str,
    theme: Theme,
    time_granularity: ChartTimeGranularity = "day",
    y_scale: ChartYScale = "compact_number",
    stack_mode: SecurityTripleStackMode = "absolute",
) -> bytes:
    """Three stacked areas from triple ``(mitigated, served_cf, served_origin)``.

    Drawn bottom→top: **mitigated**, **Served by origin**, **Served by Cloudflare**
    so the largest pass bucket (usually Cloudflare) sits at the stack top.

    ``stack_mode="percent"``: each day sums to 100% (share of sampled requests).
    """
    fig_w = min(theme.content_width_in(), 7.1)
    fig_h = fig_w * 0.35
    fig, ax = plt.subplots(figsize=(fig_w, fig_h), facecolor="white")
    tlist = list(triples)
    if not dates:
        ax.text(0.5, 0.5, "No data", ha="center", va="center", color=theme.muted)
    else:
        segments = _stacked_triple_segments(tlist)
        c_mit = theme.section_blue
        fill_mit = to_rgba(c_mit, 0.45)
        c_or = theme.muted
        fill_or = to_rgba(c_or, 0.35)
        c_cf = theme.primary
        fill_cf = to_rgba(c_cf, 0.28)
        ymax = 0.0
        for cx, mit, srv_cf, srv_or in segments:
            if stack_mode == "percent":
                mit, srv_cf, srv_or = _triple_to_percent_stack(mit, srv_cf, srv_or)
            # mitigated, served_origin, served_cf - stack origin then CF on top.
            d1 = [mit[i] + srv_or[i] for i in range(len(cx))]
            d2 = [mit[i] + srv_or[i] + srv_cf[i] for i in range(len(cx))]
            for i in range(len(cx)):
                ymax = max(ymax, d2[i])
            ax.fill_between(cx, 0, mit, color=fill_mit, linewidth=0, interpolate=True)
            ax.fill_between(cx, mit, d1, color=fill_or, linewidth=0, interpolate=True)
            ax.fill_between(cx, d1, d2, color=fill_cf, linewidth=0, interpolate=True)
            ax.plot(cx, mit, color=c_mit, linewidth=1.0, solid_capstyle="round")
            ax.plot(cx, d1, color=c_or, linewidth=1.15, solid_capstyle="round")
            ax.plot(cx, d2, color=c_cf, linewidth=1.25, solid_capstyle="round")

        if stack_mode == "percent":
            ax.set_ylim(0, 100)
        elif ymax > 0:
            ax.set_ylim(0, ymax * 1.05)

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
        if stack_mode == "percent":
            y_fmt = _format_y_tick_percent
        else:
            y_fmt = _format_y_tick_bytes if y_scale == "bytes" else _format_y_tick_cf
        ax.yaxis.set_major_formatter(ticker.FuncFormatter(y_fmt))
        ax.tick_params(axis="y", labelsize=7, colors=theme.muted)
        ax.grid(axis="both", linestyle="-", alpha=0.2, color=theme.border)
        ax.set_axisbelow(True)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

        if segments:
            h_mit = Patch(facecolor=fill_mit, edgecolor=c_mit, linewidth=1.0, label=legend_bottom)
            h_or = Patch(facecolor=fill_or, edgecolor=c_or, linewidth=1.0, label=legend_top)
            h_cf = Patch(facecolor=fill_cf, edgecolor=c_cf, linewidth=1.0, label=legend_mid)
            # Legend top-to-bottom = stack top-to-bottom: Cloudflare, origin, mitigated.
            ax.legend(
                handles=[h_cf, h_or, h_mit],
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


def line_chart_triple_bytes(
    dates: Sequence[date],
    triples: Sequence[StackedTriplePoint],
    *,
    title: str,
    subtitle: str,
    legend_mit: str,
    legend_cf: str,
    legend_or: str,
    theme: Theme,
    time_granularity: ChartTimeGranularity = "day",
) -> bytes:
    """Three lines from ``(mitigated, served_cf, served_origin)`` per time bucket.

    Missing buckets (any ``None``) become NaN so Matplotlib breaks the lines.
    Semi-transparent fills from zero + small round markers at each point.
    """
    _fill_alpha = 0.22
    _marker_ms = 4.0
    _marker_edgewidth = 0.55
    fig_w = min(theme.content_width_in(), 7.1)
    fig_h = fig_w * 0.35
    fig, ax = plt.subplots(figsize=(fig_w, fig_h), facecolor="white")
    if not dates:
        ax.text(0.5, 0.5, "No data", ha="center", va="center", color=theme.muted)
    else:
        x = list(range(len(dates)))
        y_m: list[float] = []
        y_cf: list[float] = []
        y_o: list[float] = []
        ymax = 0.0
        for a, b, c in triples:
            if a is not None and b is not None and c is not None:
                fa, fb, fc = float(a), float(b), float(c)
                y_m.append(fa)
                y_cf.append(fb)
                y_o.append(fc)
                ymax = max(ymax, fa, fb, fc)
            else:
                y_m.append(float("nan"))
                y_cf.append(float("nan"))
                y_o.append(float("nan"))

        c_mit = theme.section_blue
        c_cf = theme.primary
        c_or = theme.muted
        fill_mit = to_rgba(c_mit, _fill_alpha)
        fill_cf = to_rgba(c_cf, _fill_alpha)
        fill_or = to_rgba(c_or, _fill_alpha)
        # Fills first (back to front); lines + markers on top.
        ax.fill_between(x, 0, y_m, color=fill_mit, linewidth=0, interpolate=True, zorder=1)
        ax.fill_between(x, 0, y_o, color=fill_or, linewidth=0, interpolate=True, zorder=2)
        ax.fill_between(x, 0, y_cf, color=fill_cf, linewidth=0, interpolate=True, zorder=3)
        plot_kw: dict = {
            "linewidth": 1.35,
            "solid_capstyle": "round",
            "marker": "o",
            "markersize": _marker_ms,
            "markeredgewidth": _marker_edgewidth,
            "markeredgecolor": "white",
            "zorder": 4,
        }
        ax.plot(x, y_m, color=c_mit, markerfacecolor=c_mit, label=legend_mit, **plot_kw)
        ax.plot(x, y_cf, color=c_cf, markerfacecolor=c_cf, label=legend_cf, **plot_kw)
        ax.plot(x, y_o, color=c_or, markerfacecolor=c_or, label=legend_or, **plot_kw)

        if ymax > 0:
            ax.set_ylim(0, ymax * 1.08)

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

        if any(math.isfinite(v) for v in y_m + y_cf + y_o):
            h_m = Line2D(
                [0],
                [0],
                color=c_mit,
                lw=1.35,
                marker="o",
                markersize=_marker_ms * 0.9,
                markerfacecolor=c_mit,
                markeredgecolor="white",
                markeredgewidth=_marker_edgewidth,
                label=legend_mit,
            )
            h_cf_l = Line2D(
                [0],
                [0],
                color=c_cf,
                lw=1.35,
                marker="o",
                markersize=_marker_ms * 0.9,
                markerfacecolor=c_cf,
                markeredgecolor="white",
                markeredgewidth=_marker_edgewidth,
                label=legend_cf,
            )
            h_o = Line2D(
                [0],
                [0],
                color=c_or,
                lw=1.35,
                marker="o",
                markersize=_marker_ms * 0.9,
                markerfacecolor=c_or,
                markeredgecolor="white",
                markeredgewidth=_marker_edgewidth,
                label=legend_or,
            )
            ax.legend(
                handles=[h_m, h_cf_l, h_o],
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


def prepare_triple_stacked_daily_metric_series(
    points: Sequence[tuple[date, tuple[int | None, int | None, int | None]]],
    theme: Theme,
    *,
    chart_title: str,
    legend_bottom: str,
    legend_mid: str,
    legend_top: str,
    y_scale: ChartYScale = "compact_number",
    stack_mode: SecurityTripleStackMode = "absolute",
) -> tuple[bytes, str]:
    as_floats: list[tuple[date, StackedTriplePoint]] = [
        (
            d,
            (
                float(a) if a is not None else None,
                float(b) if b is not None else None,
                float(c) if c is not None else None,
            ),
        )
        for d, (a, b, c) in points
    ]
    d, trips, sub, gran = aggregate_triple_stacked_for_chart(as_floats)
    if len(d) < 2:
        return b"", sub
    png = stacked_area_chart_triple_bytes(
        d,
        trips,
        title=chart_title,
        subtitle=sub,
        legend_bottom=legend_bottom,
        legend_mid=legend_mid,
        legend_top=legend_top,
        theme=theme,
        time_granularity=gran,
        y_scale=y_scale,
        stack_mode=stack_mode,
    )
    return png, sub


def prepare_triple_line_daily_metric_series(
    points: Sequence[tuple[date, tuple[int | None, int | None, int | None]]],
    theme: Theme,
    *,
    chart_title: str,
    legend_mit: str,
    legend_cf: str,
    legend_or: str,
) -> tuple[bytes, str]:
    """Same bucketing as stacked triple; renders three absolute-count lines."""
    as_floats: list[tuple[date, StackedTriplePoint]] = [
        (
            d,
            (
                float(a) if a is not None else None,
                float(b) if b is not None else None,
                float(c) if c is not None else None,
            ),
        )
        for d, (a, b, c) in points
    ]
    d, trips, sub, gran = aggregate_triple_stacked_for_chart(as_floats)
    if len(d) < 2:
        return b"", sub
    png = line_chart_triple_bytes(
        d,
        trips,
        title=chart_title,
        subtitle=sub,
        legend_mit=legend_mit,
        legend_cf=legend_cf,
        legend_or=legend_or,
        theme=theme,
        time_granularity=gran,
    )
    return png, sub


def prepare_stacked_daily_metric_series(
    points: Sequence[tuple[date, tuple[int | None, int | None]]],
    theme: Theme,
    *,
    chart_title: str,
    bottom_legend: str,
    top_legend: str,
    y_scale: ChartYScale = "compact_number",
) -> tuple[bytes, str]:
    """Stacked cached + uncached (or any bottom/top pair) from per-day ints."""
    as_floats: list[tuple[date, StackedPoint]] = [
        (
            d,
            (
                float(b) if b is not None else None,
                float(u) if u is not None else None,
            ),
        )
        for d, (b, u) in points
    ]
    d, pairs, sub, gran = aggregate_stacked_pairs_for_chart(as_floats)
    if len(d) < 2:
        return b"", sub
    png = stacked_area_chart_bytes(
        d,
        pairs,
        title=chart_title,
        subtitle=sub,
        bottom_legend=bottom_legend,
        top_legend=top_legend,
        theme=theme,
        time_granularity=gran,
        y_scale=y_scale,
    )
    return png, sub


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
