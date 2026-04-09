from __future__ import annotations

import json
from datetime import date

from cloudflare_executive_report.config import AppConfig, ZoneEntry
from cloudflare_executive_report.sync.options import SyncMode, SyncOptions
from cloudflare_executive_report.sync.orchestrator import select_previous_report_for_period


def _write_report(
    path, *, start: str, end: str, zone_id: str = "z1", report_type: str | None = None
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "report_period": {"start": start, "end": end, "timezone": "UTC"},
        "zones": [{"zone_id": zone_id, "zone_name": "example.com", "http": {}}],
    }
    if report_type is not None:
        payload["report_type"] = report_type
    path.write_text(
        json.dumps(payload),
        encoding="utf-8",
    )


def _cfg(tmp_path) -> AppConfig:
    return AppConfig(
        api_token="x",
        cache_dir=str(tmp_path / "cache"),
        output_dir=str(tmp_path / "out"),
        zones=[ZoneEntry(id="z1", name="example.com")],
    )


def test_select_previous_range_prefers_nearest_valid_prior(tmp_path):
    cfg = _cfg(tmp_path)
    _write_report(cfg.report_previous_path(), start="2026-04-03", end="2026-04-04")
    _write_report(
        cfg.report_history_dir() / "cf_report_2026-04-08_100000.json",
        start="2026-04-01",
        end="2026-04-02",
    )
    opts = SyncOptions(mode=SyncMode.range, start="2026-04-03", end="2026-04-04")
    prev = select_previous_report_for_period(
        cfg,
        current_start="2026-04-03",
        current_end="2026-04-04",
        zone_id="z1",
        opts=opts,
    )
    assert prev is not None
    assert prev["report_period"]["start"] == "2026-04-01"
    assert prev["report_period"]["end"] == "2026-04-02"


def test_select_previous_last_week_uses_expected_week_window(tmp_path):
    cfg = _cfg(tmp_path)
    _write_report(
        cfg.report_history_dir() / "cf_report_2026-04-08_100000.json",
        start="2026-03-23",
        end="2026-03-29",
    )
    _write_report(
        cfg.report_previous_path(),
        start="2026-03-20",
        end="2026-03-26",
    )
    opts = SyncOptions(mode=SyncMode.last_week)
    prev = select_previous_report_for_period(
        cfg,
        current_start="2026-03-30",
        current_end="2026-04-05",
        zone_id="z1",
        opts=opts,
        y=date(2026, 4, 7),
    )
    assert prev is not None
    assert prev["report_period"]["start"] == "2026-03-23"
    assert prev["report_period"]["end"] == "2026-03-29"


def test_select_previous_semantic_ignores_mismatched_candidate_type(tmp_path):
    cfg = _cfg(tmp_path)
    _write_report(
        cfg.report_history_dir() / "cf_report_2026-04-08_100000.json",
        start="2026-03-01",
        end="2026-03-31",
        report_type="this_year",
    )
    _write_report(
        cfg.report_previous_path(),
        start="2026-03-01",
        end="2026-03-31",
        report_type="last_month",
    )
    opts = SyncOptions(mode=SyncMode.last_month)
    prev = select_previous_report_for_period(
        cfg,
        current_start="2026-04-01",
        current_end="2026-04-30",
        zone_id="z1",
        opts=opts,
        y=date(2026, 5, 1),
    )
    assert prev is not None
    assert prev.get("report_type") == "last_month"
