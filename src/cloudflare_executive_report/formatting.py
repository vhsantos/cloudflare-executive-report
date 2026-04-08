"""Shared numeric formatting helpers."""

from __future__ import annotations

from typing import Any


def trim_decimal(v: float, digits: int = 1) -> str:
    s = f"{v:.{digits}f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s


def format_bytes_human(n: int) -> str:
    if n < 0:
        n = 0
    units = ("B", "KB", "MB", "GB", "TB")
    v = float(n)
    u = 0
    while v >= 1024 and u < len(units) - 1:
        v /= 1024.0
        u += 1
    if u == 0:
        return f"{int(v)}B"
    return f"{trim_decimal(v, 1)}{units[u]}"


def format_count_human(n: int) -> str:
    if n < 0:
        n = 0
    if n < 1000:
        return str(n)
    if n < 1_000_000:
        return f"{trim_decimal(n / 1000.0, 1)}K"
    if n < 1_000_000_000:
        return f"{trim_decimal(n / 1_000_000.0, 1)}M"
    return f"{trim_decimal(n / 1_000_000_000.0, 1)}B"


def format_count_compact(v: Any) -> str:
    n = float(v or 0)
    if n >= 1_000_000:
        return f"{trim_decimal(n / 1_000_000, 1)}M"
    if n >= 1_000:
        # Product requirement for KPI cards: rounded integer K.
        return f"{int(round(n / 1_000))}K"
    return str(int(round(n)))


def format_percent_compact(v: Any) -> str:
    return f"{trim_decimal(float(v or 0.0), 1)}%"


def format_number_compact(v: Any) -> str:
    x = float(v or 0.0)
    if abs(x) >= 10:
        return str(int(round(x)))
    return trim_decimal(x, 1)
