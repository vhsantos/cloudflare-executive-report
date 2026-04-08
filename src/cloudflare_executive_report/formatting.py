"""Shared numeric formatting helpers."""

from __future__ import annotations

from html import escape
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


def status_marker_for_pdf(level: str) -> tuple[str, str]:
    """Return (marker, color) for PDF status labels.

    Uses PDF-safe symbols/text markers and falls back to pure ASCII markers on error.
    """
    normalized = str(level or "").strip().lower()
    colors = {
        "positive": "#16A34A",
        "info": "#2563EB",
        "warning": "#D97706",
        "critical": "#DC2626",
        "action": "#2563EB",
    }
    safe_markers = {
        "positive": "✔",
        "info": "[i]",
        "warning": "(!)",
        "critical": "✖",
        "action": "[>]",
    }
    ascii_markers = {
        "positive": "[OK]",
        "info": "[i]",
        "warning": "[!]",
        "critical": "[!!]",
        "action": "[>]",
    }
    if normalized not in colors:
        normalized = "info"
    try:
        marker = safe_markers[normalized]
        _ = marker.encode("utf-8")
    except Exception:
        marker = ascii_markers[normalized]
    return marker, colors[normalized]


def parse_status_prefixed_text(text: str) -> tuple[str, str]:
    """Parse catalog-style prefixes and return (level, clean_text)."""
    raw = str(text or "").strip()
    if raw.startswith("[OK] "):
        return "positive", raw[5:].strip()
    if raw.startswith("[i] "):
        return "info", raw[4:].strip()
    if raw.startswith("[!] "):
        return "warning", raw[4:].strip()
    if raw.startswith("[!!] "):
        return "critical", raw[5:].strip()
    return "info", raw


def format_pdf_status_line(text: str, *, level: str | None = None) -> str:
    """Build escaped, colorized status line markup for ReportLab Paragraph."""
    resolved_level, resolved_text = (
        (str(level).strip().lower(), str(text or "").strip())
        if level is not None
        else parse_status_prefixed_text(text)
    )
    marker, color = status_marker_for_pdf(resolved_level)
    return f"<font color='{color}'><b>{escape(marker)}</b></font> {escape(resolved_text)}"
