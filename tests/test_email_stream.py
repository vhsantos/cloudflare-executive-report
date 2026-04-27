from datetime import date

from cloudflare_executive_report.aggregators.email import build_email_section
from cloudflare_executive_report.fetchers.email import EmailFetcher


def test_email_aggregator_minimal():
    # Minimal payload test
    api_days = [
        {
            "erg_metrics": [{"action": "forward", "count": 10}],
            "erg_dmarc_metrics": [
                {
                    "dmarc": 10,
                    "spfPass": 10,
                    "dkimPass": 10,
                    "totalMatchingMessages": 10,
                }
            ],
            "top_sources": [],
            "dns_dmarc_policy": "reject",
            "dns_spf_policy": "hardfail",
            "dns_dkim_configured": True,
            "email_routing_enabled": True,
            "email_routing_status": "active",
            "routing_rules_count": 5,
        }
    ]
    section = build_email_section(api_days)
    assert section["forwarded"] == 10
    assert section["dns_dmarc_policy"] == "reject"
    assert section["dmarc_pass_rate_pct"] == 100.0


def test_email_fetcher_retention():
    fetcher = EmailFetcher()
    # GraphQL retention is usually 90 days, let's assume 30 for testing if needed
    # but the common logic handles it.
    assert fetcher.outside_retention(date(2000, 1, 1), plan_legacy_id="free") is True
