from cloudflare_executive_report.executive.phrase_catalog import render_phrase
from cloudflare_executive_report.executive.rules import (
    build_rule_messages,
    evaluate_comparison_gate,
)


def _report_with_zone(zone_id: str, *, start: str, end: str, include_streams: bool = True) -> dict:
    zone = {"zone_id": zone_id}
    if include_streams:
        zone["http"] = {"total_requests": 10}
        zone["security"] = {"mitigated_count": 1}
        zone["dns"] = {"total_queries": 1}
    return {"report_period": {"start": start, "end": end}, "zones": [zone]}


def test_comparison_gate_first_report_phrase():
    gate = evaluate_comparison_gate(
        current_zone_id="z1",
        previous_report=None,
        current_period={"start": "2026-04-01", "end": "2026-04-07"},
    )
    assert gate.allowed is False
    assert gate.warning is not None
    assert gate.warning.message == render_phrase("no_comparison.first_report")


def test_comparison_gate_period_mismatch_phrase():
    prev = _report_with_zone("z1", start="2026-03-01", end="2026-03-30")
    gate = evaluate_comparison_gate(
        current_zone_id="z1",
        previous_report=prev,
        current_period={"start": "2026-04-01", "end": "2026-04-07"},
    )
    assert gate.allowed is False
    assert "Comparison skipped: previous period" in gate.warning.message


def test_correlation_origin_overloaded_uses_exact_phrase():
    current_zone = {
        "zone_health": {},
        "http": {},
        "security": {"mitigation_rate_pct": 0.0},
        "cache": {"cache_hit_ratio": 30.0},
        "http_adaptive": {"status_5xx_rate_pct": 0.8, "origin_response_duration_avg_ms": 600},
        "dns_records": {},
        "audit": {"total_events": 0},
        "certificates": {},
    }
    out = build_rule_messages(
        current_zone=current_zone, previous_zone=None, comparison_allowed=False
    )
    texts = [m.message for m in out["correlations"]]
    assert any(
        "Origin overloaded: high error rate (0.8%) with slow response (600ms)" == t for t in texts
    )


def test_action_rules_migrated_from_summary_logic():
    current_zone = {
        "zone_name": "example.com",
        "zone_health": {
            "always_https": "off",
            "dnssec_status": "disabled",
            "ssl_mode": "full",
            "security_rules_active": 0,
        },
        "http": {"total_requests": 100, "encrypted_requests": 80},
        "security": {},
        "cache": {},
        "http_adaptive": {},
        "dns_records": {"apex_unproxied_a_aaaa": 1},
        "audit": {"total_events": 51},
        "certificates": {"expiring_in_30_days": 5},
    }
    out = build_rule_messages(
        current_zone=current_zone,
        previous_zone=None,
        comparison_allowed=False,
    )
    action_keys = [m.phrase_key for m in out["actions"]]
    action_texts = [m.message for m in out["actions"]]
    assert "action.enable_always_https" in action_keys
    assert "action.review_dnssec" in action_keys
    assert "action.review_ssl_mode" in action_keys
    assert "action.review_waf_posture" in action_keys
    assert "action.enable_apex_proxy" in action_keys
    assert "action.plan_tls_renewal" in action_keys
    assert "action.review_audit_activity" in action_keys
    assert "Enable Always Use HTTPS - redirects HTTP to HTTPS for all traffic." in action_texts
    assert "Enable DNSSEC - prevents DNS spoofing and domain hijacking." in action_texts
    assert "Change SSL mode to Full (Strict) for end-to-end encryption." in action_texts
    assert "Review Web Application Firewall (WAF) and rate-limiting baseline." in action_texts
    assert "Enable proxy on apex A/AAAA record - hides origin IP." in action_texts
    assert "Renew TLS certificate before expiry - prevents outages." in action_texts
    assert "Review audit log - check for unauthorized changes." in action_texts


def test_all_action_phrase_keys_are_reachable_by_rules():
    current_zone = {
        "zone_name": "example.com",
        "zone_health": {
            "always_https": "off",
            "dnssec_status": "disabled",
            "ssl_mode": "flexible",
            "security_rules_active": 0,
        },
        "http": {
            "total_requests": 100,
            "encrypted_requests": 80,
            "total_bandwidth_bytes": 0,
            "cache_hit_ratio": 0.0,
        },
        "security": {},
        "cache": {},
        "http_adaptive": {},
        "dns_records": {"apex_unproxied_a_aaaa": 1},
        "audit": {"total_events": 51},
        "certificates": {"expiring_in_30_days": 5},
    }
    out = build_rule_messages(
        current_zone=current_zone,
        previous_zone=None,
        comparison_allowed=False,
    )
    action_keys = {m.phrase_key for m in out["actions"]}
    expected = {
        "action.enable_always_https",
        "action.review_dnssec",
        "action.review_ssl_mode",
        "action.review_waf_posture",
        "action.enable_apex_proxy",
        "action.plan_tls_renewal",
        "action.review_audit_activity",
    }
    assert action_keys == expected
