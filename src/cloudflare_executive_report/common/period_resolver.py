"""Shared period and metadata resolution for sync/report flows.

This module provides canonical report type normalization, semantic period
resolution, baseline period derivation, and deterministic fingerprint building.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from typing import Any, Protocol

from cloudflare_executive_report.common.dates import (
    last_n_complete_days,
    month_bounds,
    week_bounds,
    year_bounds,
)


class _SyncOptionsLike(Protocol):
    """Minimal options contract required by resolver helpers."""

    mode: Any
    last_n: int | None
    start: str | None
    end: str | None


_SEMANTIC_REPORT_TYPES = {
    "yesterday",
    "last_week",
    "this_week",
    "last_month",
    "this_month",
    "last_year",
    "this_year",
}


def normalize_report_type(raw: object) -> str | None:
    """Normalize raw report type text to a supported canonical value."""
    s = str(raw or "").strip().lower()
    if not s:
        return None
    if s in _SEMANTIC_REPORT_TYPES or s in {"custom", "incremental"}:
        return s
    if s.startswith("last_"):
        tail = s[5:]
        if tail.isdigit() and int(tail) >= 1:
            return s
    return None


def _mode_name(mode: Any) -> str:
    """Return normalized mode name from enum-like or string values."""
    return str(getattr(mode, "value", mode))


def report_type_for_options(opts: _SyncOptionsLike) -> str:
    """Derive report_type from sync/report option mode values."""
    mode_name = _mode_name(opts.mode)
    if mode_name == "range":
        return "custom"
    if mode_name == "incremental":
        return "incremental"
    if mode_name == "last_n":
        n = int(opts.last_n or 0)
        return f"last_{max(n, 1)}"
    return mode_name


def semantic_current_bounds(
    *,
    report_type: str,
    y: date,
    today: date,
) -> tuple[date, date] | None:
    """Resolve current semantic period bounds for a report_type."""
    if report_type == "yesterday":
        return y, y
    if report_type == "last_week":
        this_week_start, _ = week_bounds(y)
        prev_week_end = this_week_start - timedelta(days=1)
        return week_bounds(prev_week_end)
    if report_type == "this_week":
        start, _ = week_bounds(today)
        return start, today
    if report_type == "last_month":
        this_month_start, _ = month_bounds(y)
        prev_month_day = this_month_start - timedelta(days=1)
        return month_bounds(prev_month_day)
    if report_type == "this_month":
        start, _ = month_bounds(today)
        return start, today
    if report_type == "last_year":
        return date(today.year - 1, 1, 1), date(today.year - 1, 12, 31)
    if report_type == "this_year":
        start, _ = year_bounds(today)
        return start, today
    return None


def semantic_baseline_bounds(
    *,
    report_type: str,
    y: date,
    today: date,
) -> tuple[date, date] | None:
    """Resolve semantic baseline bounds for comparison against current period."""
    if report_type == "yesterday":
        d = y - timedelta(days=1)
        return d, d
    if report_type == "last_week":
        this_week_start, _ = week_bounds(y)
        prev_week_end = this_week_start - timedelta(days=1)
        prev_week_start, _ = week_bounds(prev_week_end)
        return prev_week_start - timedelta(days=7), prev_week_start - timedelta(days=1)
    if report_type == "this_week":
        this_week_start, _ = week_bounds(today)
        prev_week_end = this_week_start - timedelta(days=1)
        return week_bounds(prev_week_end)
    if report_type == "last_month":
        this_month_start, _ = month_bounds(y)
        prev_month_day = this_month_start - timedelta(days=1)
        prev_month_start, _ = month_bounds(prev_month_day)
        month_before_prev = prev_month_start - timedelta(days=1)
        return month_bounds(month_before_prev)
    if report_type == "this_month":
        this_month_start, _ = month_bounds(today)
        prev_month_day = this_month_start - timedelta(days=1)
        prev_start, prev_end = month_bounds(prev_month_day)
        current_start, current_end = month_bounds(today)
        current_span = (today - current_start).days + 1
        end_day = min(prev_start.day + current_span - 1, prev_end.day)
        return prev_start, date(prev_start.year, prev_start.month, end_day)
    if report_type == "last_year":
        return date(y.year - 2, 1, 1), date(y.year - 2, 12, 31)
    if report_type == "this_year":
        current_start, _ = year_bounds(today)
        return date(current_start.year - 1, 1, 1), date(current_start.year - 1, 12, 31)
    return None


def resolved_period_for_options(
    *,
    opts: _SyncOptionsLike,
    y: date,
    today: date,
) -> tuple[date, date] | None:
    """Resolve explicit period bounds from options when mode is period-based."""
    rtype = report_type_for_options(opts)
    semantic = semantic_current_bounds(report_type=rtype, y=y, today=today)
    if semantic is not None:
        return semantic
    mode_name = _mode_name(opts.mode)
    if mode_name == "last_n" and opts.last_n is not None:
        return last_n_complete_days(opts.last_n, yesterday=y)
    if mode_name == "range" and opts.start and opts.end:
        return date.fromisoformat(opts.start), date.fromisoformat(opts.end)
    return None


def build_data_fingerprint(
    *,
    start: str,
    end: str,
    top: int,
    types: list[str] | tuple[str, ...] | set[str] | frozenset[str],
    include_today: bool,
) -> dict[str, Any]:
    """Build canonical fingerprint payload for report reuse checks.

    Note: zones are intentionally excluded so subsets can reuse snapshots.
    """
    return {
        "start": str(start),
        "end": str(end),
        "top": int(top),
        "types": sorted({str(t).strip().lower() for t in types if str(t).strip()}),
        "include_today": bool(include_today),
    }


def compute_fingerprint_hash(fingerprint: dict[str, Any]) -> str:
    """Compute a stable SHA-256 hash (16 chars) of the fingerprint dict."""
    # sort_keys=True guarantees stable JSON serialization
    serialized = json.dumps(fingerprint, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]
