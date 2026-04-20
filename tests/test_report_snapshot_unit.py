"""Unit tests for report/snapshot.py."""

from __future__ import annotations

from pathlib import Path

from cloudflare_executive_report.report.snapshot import load_report_json, save_report_json


def test_load_report_json_missing(tmp_path: Path) -> None:
    assert load_report_json(tmp_path / "missing.json") is None


def test_load_report_json_invalid(tmp_path: Path) -> None:
    p = tmp_path / "invalid.json"
    p.write_text("not json")
    assert load_report_json(p) is None


def test_save_load_roundtrip(tmp_path: Path) -> None:
    p = tmp_path / "report.json"
    data = {"hello": "world"}
    save_report_json(p, data)
    loaded = load_report_json(p)
    assert loaded == data
