"""Pick a prior report JSON to use as baseline for executive comparisons."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from cloudflare_executive_report.common.dates import parse_ymd, utc_today, utc_yesterday
from cloudflare_executive_report.common.period_resolver import (
    normalize_report_type,
    report_type_for_options,
    semantic_baseline_bounds,
)
from cloudflare_executive_report.config import AppConfig
from cloudflare_executive_report.report.snapshot import load_report_json
from cloudflare_executive_report.sync.options import SyncOptions


def find_previous_zone_in_report(
    previous_report: dict[str, Any] | None, zone_id: str
) -> dict[str, Any] | None:
    """Return the zone object from a report dict for the given zone id, if present."""
    if not isinstance(previous_report, dict):
        return None
    for zone in previous_report.get("zones") or []:
        if isinstance(zone, dict) and str(zone.get("zone_id") or "") == zone_id:
            return zone
    return None


def _report_period_bounds(report: dict[str, Any] | None) -> tuple[date, date] | None:
    if not isinstance(report, dict):
        return None
    period = report.get("report_period")
    if not isinstance(period, dict):
        return None
    start = str(period.get("start") or "").strip()
    end = str(period.get("end") or "").strip()
    if not start or not end:
        return None
    try:
        return parse_ymd(start), parse_ymd(end)
    except ValueError:
        return None


def _report_has_zone(report: dict[str, Any] | None, zone_id: str) -> bool:
    return find_previous_zone_in_report(report, zone_id) is not None


def _iter_baseline_candidates(cfg: AppConfig) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[Path] = set()
    p = cfg.report_previous_path()
    if p.is_file():
        seen.add(p.resolve())
        rep = load_report_json(p)
        if rep is not None:
            out.append(rep)
    hist = cfg.report_history_dir()
    if hist.is_dir():
        for f in sorted(hist.glob("cf_report_*.json"), reverse=True):
            rf = f.resolve()
            if rf in seen:
                continue
            seen.add(rf)
            rep = load_report_json(f)
            if rep is not None:
                out.append(rep)
    return out


def select_previous_report_for_period(
    cfg: AppConfig,
    *,
    current_start: str,
    current_end: str,
    zone_id: str,
    opts: SyncOptions,
    y: date | None = None,
) -> dict[str, Any] | None:
    """Choose the best prior report JSON for baseline comparison for this zone and window."""
    try:
        cs = parse_ymd(current_start)
        ce = parse_ymd(current_end)
    except ValueError:
        return None
    current_report_type = report_type_for_options(opts)
    baseline_expected = semantic_baseline_bounds(
        report_type=current_report_type,
        y=y or utc_yesterday(),
        today=utc_today(),
    )
    current_len = (ce - cs).days + 1
    best: tuple[date, dict[str, Any]] | None = None
    for rep in _iter_baseline_candidates(cfg):
        period = _report_period_bounds(rep)
        if period is None:
            continue
        ps, pe = period
        if pe >= cs:
            continue
        if ps == cs and pe == ce:
            continue
        if not _report_has_zone(rep, zone_id):
            continue
        candidate_type = normalize_report_type(rep.get("report_type"))
        if baseline_expected is not None and candidate_type is not None:
            if candidate_type not in {
                current_report_type,
                "custom",
                "incremental",
            } and not candidate_type.startswith("last_"):
                continue
        if baseline_expected is not None:
            if (ps, pe) != baseline_expected:
                continue
        else:
            if ((pe - ps).days + 1) != current_len:
                continue
        if best is None or pe > best[0]:
            best = (pe, rep)
    return best[1] if best is not None else None
