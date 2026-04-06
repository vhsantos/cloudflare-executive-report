from cloudflare_executive_report.executive_summary import build_executive_summary


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
        warnings=[],
    )
    assert out["verdict"] == "healthy"
    assert out["kpis"]["security"]["threats_mitigated"] == 200
    assert out["kpis"]["security"]["mitigated_events_human"] == "200"
    assert out["kpis"]["security"]["mitigation_rate_pct"] == 0.4
    assert "blocked or challenged" in out["takeaways"][1]


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
        warnings=["No DNS cache entry for zone example.com on 2026-04-01"],
    )
    assert out["verdict"] == "critical"
    assert "zone_status=pending" in out["verdict_reasons"]
    assert "warnings_present" in out["verdict_reasons"]
    assert out["warnings_count"] == 1
    assert len(out["actions"]) == 3


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
        warnings=[],
    )
    assert out["kpis"]["security"]["threats_mitigated"] == 7
