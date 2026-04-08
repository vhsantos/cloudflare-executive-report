from cloudflare_executive_report.executive.summary import build_executive_summary


def test_build_executive_summary_healthy_zone():
    out = build_executive_summary(
        zone_name="example.com",
        zone_health={
            "zone_status": "active",
            "ssl_mode": "strict",
            "always_https": "on",
            "security_level": "medium",
            "dnssec_status": "active",
            "ddos_protection": "on",
            "security_rules_active": 3,
        },
        dns={"total_queries": 1000, "average_qps": 1.2},
        http={
            "total_requests": 50000,
            "total_requests_human": "50K",
            "cache_hit_ratio": 55.0,
            "encrypted_requests": 49000,
            "encrypted_requests_human": "49K",
        },
        security={
            "total_events": 200,
            "mitigated_count": 200,
            "http_requests_sampled": 50000,
            "http_requests_sampled_human": "50K",
            "not_mitigated_sampled": 49800,
            "not_mitigated_sampled_human": "49.8K",
            "mitigation_rate_pct": 0.4,
            "top_actions": [
                {"action": "managed_challenge", "count": 160},
                {"action": "block", "count": 40},
            ],
        },
        cache={"cache_hit_ratio": 55.0, "served_cf_count": 20000, "served_origin_count": 30000},
        dns_records={
            "total_records": 10,
            "proxied_records": 8,
            "dns_only_records": 2,
            "apex_unproxied_a_aaaa": 0,
        },
        audit={"total_events": 3},
        certificates={
            "total_certificate_packs": 1,
            "expiring_in_30_days": 0,
            "soonest_expiry": "2026-12-01T00:00:00Z",
        },
        warnings=[],
    )
    assert out["verdict"] == "healthy"
    assert out["kpis"]["security"]["threats_mitigated"] == 200
    assert out["kpis"]["security"]["mitigated_events_human"] == "200"
    assert out["kpis"]["security"]["mitigation_rate_pct"] == 0.4
    assert any("Security level at Medium" in t for t in out["takeaways"])
    assert out["kpis"]["traffic"]["encrypted_gap_pct"] >= 0.0
    assert out["kpis"]["dns"]["average_qps"] == 1.2
    assert "takeaways_categorized" in out


def test_build_executive_summary_warning_with_warnings_and_inactive_zone():
    out = build_executive_summary(
        zone_name="example.com",
        zone_health={
            "zone_status": "pending",
            "ssl_mode": "full",
            "always_https": "off",
            "security_level": "medium",
            "dnssec_status": "disabled",
            "ddos_protection": "on",
            "security_rules_active": 0,
        },
        dns={"total_queries": 10, "average_qps": 0.1},
        http={"total_requests": 10, "total_requests_human": "10", "cache_hit_ratio": 0.0},
        security={"top_actions": [{"action": "block", "count": 1}]},
        cache=None,
        dns_records={
            "total_records": 0,
            "proxied_records": 0,
            "dns_only_records": 0,
            "apex_unproxied_a_aaaa": 0,
        },
        audit={"total_events": 0},
        certificates={
            "total_certificate_packs": 0,
            "expiring_in_30_days": 0,
            "soonest_expiry": None,
        },
        warnings=["No DNS cache entry for zone example.com on 2026-04-01"],
    )
    assert out["verdict"] == "critical"
    assert "zone_status=pending" in out["verdict_reasons"]
    assert "warnings_present" in out["verdict_reasons"]
    assert out["warnings_count"] >= 1
    assert len(out["actions"]) >= 1
    assert set(out["takeaways_categorized"].keys()) == {
        "positive_changes",
        "warnings",
        "correlations",
        "comparisons",
    }
    assert all(a not in out["takeaways"] for a in out["actions"])


def test_build_executive_summary_no_actions_when_no_action_rules_match():
    out = build_executive_summary(
        zone_name="example.com",
        zone_health={
            "zone_status": "active",
            "ssl_mode": "strict",
            "always_https": "on",
            "security_level": "high",
            "dnssec_status": "active",
            "ddos_protection": "on",
            "security_rules_active": 3,
        },
        dns={"total_queries": 1000, "average_qps": 1.2},
        http={
            "total_requests": 50000,
            "total_requests_human": "50K",
            "cache_hit_ratio": 55.0,
            "encrypted_requests": 49000,
            "encrypted_requests_human": "49K",
        },
        security={
            "total_events": 200,
            "mitigated_count": 200,
            "http_requests_sampled": 50000,
            "http_requests_sampled_human": "50K",
            "not_mitigated_sampled": 49800,
            "not_mitigated_sampled_human": "49.8K",
            "mitigation_rate_pct": 0.4,
        },
        cache={"cache_hit_ratio": 55.0, "served_cf_count": 20000, "served_origin_count": 30000},
        dns_records={
            "total_records": 10,
            "proxied_records": 8,
            "dns_only_records": 2,
            "apex_unproxied_a_aaaa": 0,
        },
        audit={"total_events": 10},
        certificates={
            "total_certificate_packs": 1,
            "expiring_in_30_days": 0,
            "soonest_expiry": "2026-12-01T00:00:00Z",
        },
        warnings=[],
    )
    assert out["actions"] == []


def test_build_executive_summary_fallback_threats_from_top_actions():
    out = build_executive_summary(
        zone_name="example.com",
        zone_health={"zone_status": "active"},
        dns={},
        http={"total_requests": 1, "total_requests_human": "1"},
        security={
            "top_actions": [
                {"action": "block", "count": 3},
                {"action": "managed_challenge", "count": 4},
                {"action": "log", "count": 9},
            ]
        },
        cache={},
        dns_records={
            "total_records": 1,
            "proxied_records": 1,
            "dns_only_records": 0,
            "apex_unproxied_a_aaaa": 0,
        },
        audit={"total_events": 0},
        certificates={
            "total_certificate_packs": 1,
            "expiring_in_30_days": 0,
            "soonest_expiry": None,
        },
        warnings=[],
    )
    assert out["kpis"]["security"]["threats_mitigated"] == 7


def test_build_executive_summary_uses_adaptive_http_takeaway_when_available():
    out = build_executive_summary(
        zone_name="example.com",
        zone_health={"zone_status": "active"},
        dns={"total_queries": 100, "average_qps": 0.2},
        http={"total_requests": 860007},
        security={"mitigated_count": 10, "mitigation_rate_pct": 1.0},
        cache={},
        http_adaptive={
            "status_4xx_rate_pct": 0.99,
            "status_5xx_rate_pct": 0.02,
            "origin_response_duration_avg_ms": 264.2,
            "latency_p50_ms": 10.0,
            "latency_p95_ms": 50.0,
        },
        dns_records={
            "total_records": 1,
            "proxied_records": 1,
            "dns_only_records": 0,
            "apex_unproxied_a_aaaa": 0,
        },
        audit={"total_events": 1},
        certificates={
            "total_certificate_packs": 1,
            "expiring_in_30_days": 0,
            "soonest_expiry": "2026-08-01T00:00:00Z",
        },
        warnings=[],
    )
    assert any(
        t.startswith("[i]") or t.startswith("[!]") or t.startswith("[OK]") for t in out["takeaways"]
    )


def test_build_executive_summary_apex_and_cert_kpi_fields():
    out = build_executive_summary(
        zone_name="vhsantos.net",
        zone_health={"zone_status": "active", "always_https": "on", "ssl_mode": "strict"},
        dns={"total_queries": 100, "average_qps": 3.97},
        http={
            "total_requests": 1_000_000,
            "total_requests_human": "1.0M",
            "encrypted_requests": 940_000,
            "encrypted_requests_human": "940K",
        },
        security={"mitigated_count": 1000, "mitigation_rate_pct": 0.1},
        cache={},
        dns_records={
            "total_records": 54,
            "proxied_records": 13,
            "dns_only_records": 41,
            "apex_unproxied_a_aaaa": 1,
        },
        audit={"total_events": 46},
        certificates={
            "total_certificate_packs": 2,
            "expiring_in_30_days": 0,
            "soonest_expiry": "2026-05-16T10:27:03Z",
        },
        warnings=[],
    )
    assert out["kpis"]["dns_records"]["apex_protection_status"].startswith("exposed")
    assert out["kpis"]["certificates"]["cert_expires_human"].startswith("2026-05-16")
    assert out["kpis"]["traffic"]["encrypted_gap_pct"] > 5.0
    assert any("Apex record not proxied" in t for t in out["takeaways"])
    assert any("Enable proxy on apex A/AAAA record - hides origin IP." in a for a in out["actions"])
