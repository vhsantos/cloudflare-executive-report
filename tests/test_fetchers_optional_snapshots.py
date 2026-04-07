from datetime import date

from cloudflare_executive_report.fetchers.audit import fetch_audit_snapshot
from cloudflare_executive_report.fetchers.certificates import fetch_certificates_snapshot
from cloudflare_executive_report.fetchers.dns_records import fetch_dns_records_snapshot


def test_fetch_dns_records_snapshot_parses_counts():
    class FakeClient:
        def get_zone(self, _zone_id: str):
            return {"name": "example.com"}

        def list_dns_records(self, _zone_id: str, *, per_page: int = 100):
            _ = per_page
            return [
                {"type": "A", "name": "example.com", "proxied": False},
                {"type": "A", "name": "www.example.com", "proxied": True},
                {"type": "TXT", "name": "example.com"},
            ]

    out = fetch_dns_records_snapshot(FakeClient(), "z", date(2026, 4, 1))
    assert out["total_records"] == 3
    assert out["proxied_records"] == 1
    assert out["dns_only_records"] == 1
    assert out["apex_unproxied_a_aaaa"] == 1


def test_fetch_audit_snapshot_parses_basic():
    class FakeClient:
        def get_zone(self, _zone_id: str):
            return {"account": {"id": "acc"}}

        def list_account_audit_logs(
            self, _account_id: str, *, since: str, before: str, limit: int = 100
        ):
            _ = (since, before, limit)
            return [
                {"action": {"type": "update"}, "actor": {"email": "a@example.com"}},
                {"action": {"type": "update"}, "actor": {"email": "a@example.com"}},
            ]

    out = fetch_audit_snapshot(
        FakeClient(),
        "z",
        "2026-04-01T00:00:00Z",
        "2026-04-02T00:00:00Z",
        date(2026, 4, 1),
    )
    assert out["total_events"] == 2
    assert out["top_actions"][0]["value"] == "update"


def test_fetch_certificates_snapshot_parses_expiry():
    class FakeClient:
        def list_zone_certificate_packs(self, _zone_id: str):
            return [
                {
                    "status": "active",
                    "certificates": [
                        {"expires_on": "2026-04-20T00:00:00Z"},
                        {"expires_on": "2026-06-20T00:00:00Z"},
                    ],
                }
            ]

    out = fetch_certificates_snapshot(FakeClient(), "z", date(2026, 4, 1))
    assert out["total_certificate_packs"] == 1
    assert out["expiring_in_30_days"] == 1
    assert out["soonest_expiry"] == "2026-04-20T00:00:00Z"
