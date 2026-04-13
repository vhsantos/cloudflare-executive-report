"""PDF report CLI and smoke tests."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from cloudflare_executive_report.config import AppConfig, CoverConfig, PdfConfig, ZoneEntry
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
    assert "--refresh-health" in out


@pytest.mark.skipif(not FIXTURE_CACHE.is_dir(), reason="sample cache fixtures missing")
def test_write_report_pdf_security_smoke(tmp_path: Path) -> None:
    cfg = AppConfig(
        api_token="x",
        cache_dir=str(FIXTURE_CACHE.resolve()),
        zones=[ZoneEntry(id=ZONE_ID, name="example.com")],
        pdf=PdfConfig(profile="detailed"),
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
        pdf=PdfConfig(profile="detailed"),
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
        pdf=PdfConfig(profile="detailed"),
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
        pdf=PdfConfig(profile="detailed"),
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


@pytest.mark.skipif(not FIXTURE_CACHE.is_dir(), reason="sample cache fixtures missing")
def test_write_report_pdf_cover_config_smoke(tmp_path: Path) -> None:
    cfg = AppConfig(
        api_token="x",
        cache_dir=str(FIXTURE_CACHE.resolve()),
        zones=[ZoneEntry(id=ZONE_ID, name="example.com")],
        cover=CoverConfig(
            enabled=True,
            company_name="Turismo Lago Grey",
            logo_path="/tmp/does-not-exist.png",
            title="Cloudflare Executive Report",
            subtitle="Security & Performance Overview",
            notes="All metrics from Cloudflare Analytics API",
            prepared_for="CTO Office",
            classification="Internal Use Only",
        ),
    )
    spec = ReportSpec(
        zone_ids=[ZONE_ID],
        start="2026-04-01",
        end="2026-04-01",
        streams=("dns",),
        top=5,
    )
    out = tmp_path / "cover.pdf"
    write_report_pdf(out, cfg, spec)
    assert out.is_file()
    assert out.stat().st_size > 1000


@pytest.mark.skipif(not FIXTURE_CACHE.is_dir(), reason="sample cache fixtures missing")
def test_write_report_pdf_warns_when_executive_disabled_but_profile_not_minimal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    import logging

    cfg = AppConfig(
        api_token="x",
        cache_dir=str(FIXTURE_CACHE.resolve()),
        zones=[ZoneEntry(id=ZONE_ID, name="example.com")],
        pdf=PdfConfig(profile="executive"),
    )
    spec = ReportSpec(
        zone_ids=[ZONE_ID],
        start="2026-04-01",
        end="2026-04-01",
        streams=("dns",),
        include_executive_summary=False,
        top=5,
    )

    def _boom(*args: Any, **kwargs: Any) -> None:  # pragma: no cover
        raise AssertionError("fetch_zone_health should not run")

    monkeypatch.setattr("cloudflare_executive_report.pdf.orchestrate.fetch_zone_health", _boom)

    caplog.set_level(logging.WARNING)
    out = tmp_path / "warn_profile.pdf"
    write_report_pdf(out, cfg, spec, allow_live_health_fetch=False)
    assert out.is_file()
    assert "pdf.profile" in caplog.text
    assert "executive summary is disabled" in caplog.text


@pytest.mark.skipif(not FIXTURE_CACHE.is_dir(), reason="sample cache fixtures missing")
def test_write_report_pdf_offline_mode_does_not_fetch_health(tmp_path: Path, monkeypatch) -> None:
    cfg = AppConfig(
        api_token="x",
        cache_dir=str(FIXTURE_CACHE.resolve()),
        zones=[ZoneEntry(id=ZONE_ID, name="example.com")],
    )
    spec = ReportSpec(
        zone_ids=[ZONE_ID],
        start="2026-04-01",
        end="2026-04-01",
        streams=("dns",),
        include_executive_summary=False,
        top=5,
    )

    def _boom(*args, **kwargs):  # pragma: no cover - should never run
        raise AssertionError("fetch_zone_health should not run in offline mode")

    monkeypatch.setattr("cloudflare_executive_report.pdf.orchestrate.fetch_zone_health", _boom)

    out = tmp_path / "offline.pdf"
    write_report_pdf(out, cfg, spec, allow_live_health_fetch=False)
    assert out.is_file()
    assert out.stat().st_size > 1000


@pytest.mark.skipif(not FIXTURE_CACHE.is_dir(), reason="sample cache fixtures missing")
def test_write_report_pdf_executive_profile_skips_security_stream(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    touched: list[str] = []

    def _stub_security(*args: Any, **kwargs: Any) -> None:
        touched.append("security")

    monkeypatch.setattr(
        "cloudflare_executive_report.pdf.orchestrate.append_security_stream",
        _stub_security,
    )
    cfg = AppConfig(
        api_token="x",
        cache_dir=str(FIXTURE_CACHE.resolve()),
        zones=[ZoneEntry(id=ZONE_ID, name="example.com")],
        pdf=PdfConfig(profile="executive"),
    )
    spec = ReportSpec(
        zone_ids=[ZONE_ID],
        start="2026-04-01",
        end="2026-04-01",
        streams=("security",),
        top=5,
    )
    out = tmp_path / "executive_profile.pdf"
    write_report_pdf(out, cfg, spec)
    assert touched == []
    assert out.is_file()


@pytest.mark.skipif(not FIXTURE_CACHE.is_dir(), reason="sample cache fixtures missing")
def test_write_report_pdf_detailed_profile_renders_security_stream(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    touched: list[str] = []

    def _stub_security(*args: Any, **kwargs: Any) -> None:
        touched.append("security")

    monkeypatch.setattr(
        "cloudflare_executive_report.pdf.orchestrate.append_security_stream",
        _stub_security,
    )
    cfg = AppConfig(
        api_token="x",
        cache_dir=str(FIXTURE_CACHE.resolve()),
        zones=[ZoneEntry(id=ZONE_ID, name="example.com")],
        pdf=PdfConfig(profile="detailed"),
    )
    spec = ReportSpec(
        zone_ids=[ZONE_ID],
        start="2026-04-01",
        end="2026-04-01",
        streams=("security",),
        top=5,
    )
    out = tmp_path / "detailed_profile.pdf"
    write_report_pdf(out, cfg, spec)
    assert touched == ["security"]
