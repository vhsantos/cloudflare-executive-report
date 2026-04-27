from datetime import date
from unittest.mock import MagicMock, patch

from cloudflare_executive_report.aggregators.email import build_email_section
from cloudflare_executive_report.fetchers.email import (
    EmailFetcher,
    _parse_dns_policies,
    fetch_email_for_bounds,
)


def test_email_aggregator_multi_day():
    # Test multi-day aggregation and failure rate calculation
    api_days = [
        {
            "date": "2026-01-01",
            "erg_metrics": [
                {"action": "forward", "status": "delivered", "count": 100},
                {"action": "forward", "status": "deliveryfailed", "count": 10},
            ],
            "erg_dmarc_metrics": [{"dmarc": 90, "totalMatchingMessages": 110}],
            "email_routing_enabled": True,
        },
        {
            "date": "2026-01-02",
            "erg_metrics": [
                {"action": "drop", "count": 20},
                {"action": "reject", "count": 5},
            ],
            "erg_dmarc_metrics": [{"dmarc": 100, "totalMatchingMessages": 100}],
        },
    ]
    section = build_email_section(api_days)

    assert section["total_received"] == 135  # 100+10+20+5
    assert section["forwarded"] == 100
    assert section["delivery_failed"] == 10
    assert section["dropped"] == 20
    assert section["rejected"] == 5
    assert section["delivery_failed_rate_pct"] == (100.0 * 10 / 135)
    assert section["dmarc_pass_rate_pct"] == (100.0 * 190 / 210)


def test_email_aggregator_top_sources():
    api_days = [
        {
            "erg_dmarc_top_sources": [
                {
                    "sourceOrgName": "Google",
                    "totalMatchingMessages": 50,
                    "dmarc": 48,
                    "spfPass": 45,
                    "dkimPass": 49,
                },
                {
                    "sourceOrgName": "Outlook",
                    "totalMatchingMessages": 30,
                    "dmarc": 20,
                    "spfPass": 15,
                    "dkimPass": 10,
                },
            ]
        }
    ]
    section = build_email_section(api_days)
    top = section["top_sources"]
    assert len(top) == 2
    assert top[0]["sourceOrgName"] == "Google"
    assert top[0]["volume"] == 50
    assert top[0]["dmarc_pass_pct"] == 96.0
    assert top[1]["sourceOrgName"] == "Outlook"
    assert top[1]["volume"] == 30
    assert top[1]["dmarc_pass_pct"] == (100.0 * 20 / 30)


def test_parse_dns_policies():
    mock_client = MagicMock()
    # Test DMARC p=reject, SPF ~all, DKIM exists
    mock_client.list_dns_records.return_value = [
        {"name": "_dmarc.example.com", "content": '"v=DMARC1; p=reject; rua=mailto:..."'},
        {"name": "example.com", "content": "v=spf1 include:_spf.google.com ~all"},
        {"name": "google._domainkey.example.com", "content": "v=DKIM1; k=rsa; p=..."},
    ]

    dmarc, spf, dkim = _parse_dns_policies(mock_client, "zone123", "example.com")
    assert dmarc == "reject"
    assert spf == "softfail"
    assert dkim is True


def test_parse_dns_policies_variants():
    mock_client = MagicMock()
    # Test SPF hardfail and missing DMARC
    mock_client.list_dns_records.return_value = [
        {"name": "example.com", "content": "v=spf1 -all"},
    ]

    dmarc, spf, dkim = _parse_dns_policies(mock_client, "zone123", "example.com")
    assert dmarc == "none"
    assert spf == "hardfail"
    assert dkim is False


def test_email_fetcher_retention():
    fetcher = EmailFetcher()
    # Today's date is always within retention
    assert fetcher.outside_retention(date.today(), plan_legacy_id="free") is False
    # 10 years ago is outside retention
    assert fetcher.outside_retention(date(2010, 1, 1), plan_legacy_id="free") is True


def test_fetch_email_for_bounds_logic():
    mock_client = MagicMock()

    # 1. Mock DNS Policies
    mock_client.list_dns_records.return_value = [
        {"name": "_dmarc.example.com", "content": "v=DMARC1; p=quarantine"},
    ]

    # 2. Mock Email Routing Settings (Corrected method name)
    mock_client.get_email_routing_settings.return_value = {
        "enabled": True,
        "status": "active",
    }

    # 3. Mock Email Routing Rules
    mock_client.list_email_routing_rules.return_value = [
        {"enabled": True},
        {"enabled": True},
        {"enabled": False},
    ]  # 2 active rules

    # 4. Mock GraphQL with correct aliases
    mock_client.graphql.return_value = {
        "viewer": {
            "zones": [
                {
                    "erg": [
                        {"count": 100, "dimensions": {"action": "forward", "status": "delivered"}}
                    ],
                    "erg_dmarc": [
                        {
                            "sum": {
                                "totalMatchingMessages": 50,
                                "dmarc": 40,
                                "spfPass": 30,
                                "dkimPass": 35,
                            }
                        }
                    ],
                    "erg_dmarc_top": [
                        {
                            "sum": {
                                "totalMatchingMessages": 50,
                                "dmarc": 40,
                                "spfPass": 30,
                                "dkimPass": 35,
                            },
                            "dimensions": {"sourceOrgName": "Test"},
                        }
                    ],
                }
            ]
        }
    }

    result = fetch_email_for_bounds(
        mock_client, zone_id="z123", zone_name="example.com", since="2026-01-01", until="2026-01-01"
    )

    assert result["email_routing_enabled"] is True
    assert result["routing_rules_count"] == 2
    assert result["dns_dmarc_policy"] == "quarantine"
    assert len(result["erg_metrics"]) == 1
    assert result["erg_metrics"][0]["count"] == 100
    assert result["erg_dmarc_top_sources"][0]["sourceOrgName"] == "Test"


def test_fetch_email_graphql_error():
    mock_client = MagicMock()
    mock_client.list_dns_records.return_value = []
    mock_client.get_email_routing_settings.return_value = {"enabled": False}

    # Mock GraphQL error
    mock_client.graphql.return_value = {"errors": [{"message": "Some error"}]}

    result = fetch_email_for_bounds(
        mock_client, zone_id="z123", zone_name="example.com", since="2026-01-01", until="2026-01-01"
    )

    assert result["erg_metrics"] == []
    assert result["erg_dmarc_metrics"] == []


def test_email_fetcher_class_methods():
    fetcher = EmailFetcher()
    mock_client = MagicMock()

    # 1. Mock fetch (using patch for better safety)
    with patch("cloudflare_executive_report.fetchers.email.fetch_email_for_date") as mock_fetch:
        mock_fetch.return_value = {"ok": True}
        res = fetcher.fetch(mock_client, "z1", date(2026, 1, 1), zone_meta={"name": "ex.com"})
        assert res == {"ok": True}
        mock_fetch.assert_called_once()

    # 2. Mock append_live_today (using patch)
    with patch(
        "cloudflare_executive_report.fetchers.email.fetch_email_for_bounds"
    ) as mock_fetch_bounds:
        mock_fetch_bounds.return_value = {"ok": True}
        res, notes, _err = fetcher.append_live_today(
            mock_client, "z1", "ex.com", plan_legacy_id="pro", zone_meta={}
        )
        assert len(res) == 1
        assert res[0] == {"ok": True, "date": date.today().isoformat()}
        assert "Report includes today's UTC date" in notes[0]


def test_email_pdf_stream():
    from cloudflare_executive_report.pdf.layout_spec import EmailStreamLayout
    from cloudflare_executive_report.pdf.primitives import clear_render_context, initialize
    from cloudflare_executive_report.pdf.streams.email import (
        append_email_stream,
        collect_email_appendix_notes,
    )
    from cloudflare_executive_report.pdf.theme import Theme

    mock_story = []
    email_data = {
        "email_routing_enabled": True,
        "total_received": 1000,
        "dns_dmarc_policy": "reject",
        "dns_spf_policy": "hardfail",
        "dns_dkim_configured": True,
        "routing_rules_count": 5,
        "dmarc_pass_rate_pct": 99.0,
        "top_sources": [{"sourceOrgName": "Test", "volume_human": "100", "dmarc_pass_pct": 100.0}],
    }
    mock_theme = Theme()
    mock_layout = EmailStreamLayout()

    # 1. Test appendix notes
    notes = collect_email_appendix_notes(email_data, profile="executive")
    assert len(notes) > 0

    # 2. Test PDF stream appending
    initialize(mock_theme)
    try:
        append_email_stream(
            mock_story,
            zone_name="example.com",
            period_start="2026-01-01",
            period_end="2026-01-07",
            email=email_data,
            daily_forwarded=[(date(2026, 1, 1), 100)],
            daily_delivery_failed=[(date(2026, 1, 1), 0)],
            daily_dropped_rejected=[(date(2026, 1, 1), 0)],
            missing_dates=[],
            layout=mock_layout,
            theme=mock_theme,
        )
        assert len(mock_story) > 0
    finally:
        clear_render_context()


def test_email_pdf_stream_disabled():
    """Test PDF stream when email routing is disabled (early exit path)."""
    from cloudflare_executive_report.pdf.layout_spec import EmailStreamLayout
    from cloudflare_executive_report.pdf.primitives import clear_render_context, initialize
    from cloudflare_executive_report.pdf.streams.email import append_email_stream
    from cloudflare_executive_report.pdf.theme import Theme

    mock_story = []
    email_data = {
        "email_routing_enabled": False,  # Disabled
        "dns_dmarc_policy": "reject",
        "dns_spf_policy": "hardfail",
        "dns_dkim_configured": True,
    }
    mock_theme = Theme()
    mock_layout = EmailStreamLayout()

    initialize(mock_theme)
    try:
        append_email_stream(
            mock_story,
            zone_name="example.com",
            period_start="2026-01-01",
            period_end="2026-01-07",
            email=email_data,
            daily_forwarded=[],
            daily_delivery_failed=[],
            daily_dropped_rejected=[],
            missing_dates=[],
            layout=mock_layout,
            theme=mock_theme,
        )
        # Should have content (KPI row) even if disabled
        assert len(mock_story) > 0
    finally:
        clear_render_context()
