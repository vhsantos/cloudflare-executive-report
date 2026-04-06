"""PDF report CLI and smoke tests."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from cloudflare_executive_report.config import AppConfig, ZoneEntry
from cloudflare_executive_report.pdf.layout_spec import ReportSpec

pytest.importorskip("reportlab")
pytest.importorskip("matplotlib")

from cloudflare_executive_report.pdf.orchestrate import write_report_pdf  # noqa: E402

FIXTURE_CACHE = Path(__file__).resolve().parent.parent / "docs" / "sample-data" / "cache"
ZONE_ID = "a1b2c3d4e5f6789012345678abcdef01"


def test_cf_report_report_help() -> None:
    r = subprocess.run(
        [sys.executable, "-m", "cloudflare_executive_report.cli", "report", "-h"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 0
    out = r.stdout
    assert " report [OPTIONS]" in out
    assert "COMMAND [ARGS]" not in out
    assert "--last" in out and "--types" in out and "--cache-only" in out


@pytest.mark.skipif(not FIXTURE_CACHE.is_dir(), reason="sample cache fixtures missing")
def test_write_report_pdf_security_smoke(tmp_path: Path) -> None:
    cfg = AppConfig(
        api_token="x",
        cache_dir=str(FIXTURE_CACHE.resolve()),
        zones=[ZoneEntry(id=ZONE_ID, name="example.com")],
    )
    spec = ReportSpec(
        zone_ids=[ZONE_ID],
        start="2026-04-01",
        end="2026-04-01",
        streams=("security",),
        top=5,
    )
    out = tmp_path / "sec.pdf"
    write_report_pdf(out, cfg, spec)
    assert out.is_file()
    assert out.stat().st_size > 1000


@pytest.mark.skipif(not FIXTURE_CACHE.is_dir(), reason="sample cache fixtures missing")
def test_write_report_pdf_smoke(tmp_path: Path) -> None:
    cfg = AppConfig(
        api_token="x",
        cache_dir=str(FIXTURE_CACHE.resolve()),
        zones=[ZoneEntry(id=ZONE_ID, name="example.com")],
    )
    spec = ReportSpec(
        zone_ids=[ZONE_ID],
        start="2026-04-01",
        end="2026-04-01",
        streams=("dns", "http"),
        top=5,
    )
    out = tmp_path / "out.pdf"
    write_report_pdf(out, cfg, spec)
    assert out.is_file()
    assert out.stat().st_size > 1000


@pytest.mark.skipif(not FIXTURE_CACHE.is_dir(), reason="sample cache fixtures missing")
def test_write_report_pdf_security_and_cache_smoke(tmp_path: Path) -> None:
    cfg = AppConfig(
        api_token="x",
        cache_dir=str(FIXTURE_CACHE.resolve()),
        zones=[ZoneEntry(id=ZONE_ID, name="example.com")],
    )
    spec = ReportSpec(
        zone_ids=[ZONE_ID],
        start="2026-04-01",
        end="2026-04-01",
        streams=("security", "cache"),
        top=5,
    )
    out = tmp_path / "sec_cache.pdf"
    write_report_pdf(out, cfg, spec)
    assert out.is_file()
    assert out.stat().st_size > 1000


@pytest.mark.skipif(not FIXTURE_CACHE.is_dir(), reason="sample cache fixtures missing")
def test_write_report_pdf_cache_smoke(tmp_path: Path) -> None:
    cfg = AppConfig(
        api_token="x",
        cache_dir=str(FIXTURE_CACHE.resolve()),
        zones=[ZoneEntry(id=ZONE_ID, name="example.com")],
    )
    spec = ReportSpec(
        zone_ids=[ZONE_ID],
        start="2026-04-01",
        end="2026-04-01",
        streams=("cache",),
        top=5,
    )
    out = tmp_path / "cache.pdf"
    write_report_pdf(out, cfg, spec)
    assert out.is_file()
    assert out.stat().st_size > 1000
