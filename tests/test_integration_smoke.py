"""Integration smoke test: sync -> report pdf."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cloudflare_executive_report.config import AppConfig, PdfConfig, ZoneEntry
from cloudflare_executive_report.pdf.layout_spec import ReportSpec
from cloudflare_executive_report.pdf.orchestrate import write_report_pdf
from cloudflare_executive_report.sync.options import SyncMode, SyncOptions
from cloudflare_executive_report.sync.orchestrator import run_sync

ZONE_ID = "1234567890abcdef1234567890abcdef"


@pytest.fixture
def mock_client() -> MagicMock:
    client = MagicMock()
    # Mock zone metadata
    client.get_zone.return_value = {
        "id": ZONE_ID,
        "name": "test.com",
        "status": "active",
        "plan": {"legacy_id": "enterprise"},
    }

    # Mock GraphQL for all streams
    # Return a minimal valid structure that aggregators can process
    client.graphql.return_value = {
        "viewer": {
            "zones": [
                {
                    "httpRequestsAdaptiveGroups": [
                        {"count": 100, "dimensions": {"clientRequestHTTPProtocol": "HTTP/2"}}
                    ],
                    "dnsAnalyticsAdaptiveGroups": [{"count": 50, "dimensions": {"queryType": "A"}}],
                    "firewallEventsAdaptiveGroups": [
                        {"count": 10, "dimensions": {"action": "block"}}
                    ],
                    # Aliased DNS batches
                    "by_query_name": [{"count": 50, "dimensions": {"queryName": "example.com"}}],
                    "by_query_type": [{"count": 50, "dimensions": {"queryType": "A"}}],
                    "by_response": [{"count": 50, "dimensions": {"responseCode": 0}}],
                    "by_colo": [{"count": 50, "dimensions": {"coloName": "SFO"}}],
                    "by_protocol": [{"count": 50, "dimensions": {"protocol": "UDP"}}],
                    "by_ip_version": [{"count": 50, "dimensions": {"ipVersion": 4}}],
                }
            ]
        }
    }

    # Mock zone health settings
    client.sdk.zones.settings.get.return_value.model_dump.return_value = {"value": "on"}
    client.sdk.dns.dnssec.get.return_value.status = "active"
    client.sdk.zones.settings.get_all.return_value.result = []

    return client


def test_sync_to_report_integration_smoke(tmp_path: Path, mock_client: MagicMock) -> None:
    """Smoke test: sync one day of data and generate a PDF report."""
    cache_dir = tmp_path / "cache"
    output_dir = tmp_path / "output"
    cache_dir.mkdir()
    output_dir.mkdir()

    cfg = AppConfig(
        api_token="mock-token",
        cache_dir=str(cache_dir),
        output_dir=str(output_dir),
        zones=[ZoneEntry(id=ZONE_ID, name="test.com")],
        pdf=PdfConfig(profile="minimal"),
    )

    opts = SyncOptions(
        mode=SyncMode.last_n,
        last_n=1,
        types=["http", "security", "dns"],
        refresh=True,
    )

    # 1. Run Sync (mocking the client creation)
    with patch(
        "cloudflare_executive_report.sync.orchestrator.CloudflareClient", return_value=mock_client
    ):
        # We also need to mock it in write_report_pdf if it fetches live health
        with patch(
            "cloudflare_executive_report.pdf.orchestrate.CloudflareClient", return_value=mock_client
        ):
            res = run_sync(cfg, opts, write_report_json=True)
            assert res == 0

            # Check if cache files were created
            zone_cache = cache_dir / ZONE_ID
            assert zone_cache.is_dir()

            # 2. Run Report PDF
            pdf_out = output_dir / "report.pdf"
            spec = ReportSpec(
                zone_ids=[ZONE_ID],
                start="2026-04-16",  # Assuming today is 17th
                end="2026-04-16",
                streams=("http", "security", "dns"),
            )

            write_report_pdf(pdf_out, cfg, spec, sync_opts=opts)

            assert pdf_out.is_file()
            assert pdf_out.stat().st_size > 0
