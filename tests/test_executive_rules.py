from cloudflare_executive_report.executive.phrase_catalog import (
    format_line_with_severity_prefix,
    get_phrase,
)
from cloudflare_executive_report.executive.rules import (
    SECT_DELTAS,
    SECT_RISKS,
    SECT_SIGNALS,
    ExecutiveMessageFilter,
    build_executive_rule_output,
    evaluate_comparison_gate,
    exec_msg,
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
    assert gate.blocked_takeaway is not None
    assert gate.blocked_takeaway.body == str(
        get_phrase("comparison_first_report", "comparison")["text"]
    )
    assert gate.blocked_takeaway.section == SECT_DELTAS


def test_get_phrase_only_risk_has_weight() -> None:
    assert get_phrase("dnssec", "risk")["weight"] == 7
    assert get_phrase("dnssec", "win")["weight"] == 0
    assert get_phrase("dnssec", "action")["weight"] == 0
    assert get_phrase("comparison_baseline", "comparison")["weight"] == 0
    assert get_phrase("email_obfuscation", "observation")["weight"] == 0


def test_comparison_gate_period_mismatch_phrase():
    prev = _report_with_zone("z1", start="2026-03-01", end="2026-03-30")
    gate = evaluate_comparison_gate(
        current_zone_id="z1",
        previous_report=prev,
        current_period={"start": "2026-04-01", "end": "2026-04-07"},
    )
    assert gate.allowed is False
    assert "Comparison skipped: previous period" in gate.blocked_takeaway.body
    assert gate.blocked_takeaway.section == SECT_DELTAS


def test_comparison_gate_rejects_overlapping_periods():
    prev = _report_with_zone("z1", start="2026-04-01", end="2026-04-07")
    gate = evaluate_comparison_gate(
        current_zone_id="z1",
        previous_report=prev,
        current_period={"start": "2026-04-05", "end": "2026-04-11"},
    )
    assert gate.allowed is False
    assert "Comparison skipped: previous period" in gate.blocked_takeaway.body
    assert gate.blocked_takeaway.section == SECT_DELTAS


def test_comparison_gate_warning_merged_into_deltas_not_risks():
    """Gate line is a delta, not a risk (ignored for risks-only posture score)."""
    gate = evaluate_comparison_gate(
        current_zone_id="z1",
        previous_report=None,
        current_period={"start": "2026-04-01", "end": "2026-04-07"},
    )
    assert gate.blocked_takeaway is not None
    clean_zone = {
        "zone_health": {
            "ssl_mode": "strict",
            "always_https": "on",
            "security_rules_active": 1,
            "dnssec_status": "active",
            "ddos_protection": "on",
        },
        "http": {},
        "security": {},
        "cache": {},
        "http_adaptive": {},
        "dns_records": {"apex_unproxied_a_aaaa": 0},
        "audit": {"total_events": 0},
        "certificates": {"total_certificate_packs": 1, "expiring_in_30_days": 0},
    }
    out = build_executive_rule_output(
        current_zone=clean_zone,
        previous_zone=None,
        comparison_allowed=False,
        gate_warning=gate.blocked_takeaway,
    )
    delta_keys = {m.phrase_key for m in out.lines_for_section(SECT_DELTAS)}
    risk_keys = {m.phrase_key for m in out.lines_for_section(SECT_RISKS)}
    assert "comparison_first_report" in delta_keys
    assert "comparison_first_report" not in risk_keys


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
    out = build_executive_rule_output(
        current_zone=current_zone, previous_zone=None, comparison_allowed=False
    )
    texts = [m.body for m in out.lines_for_section(SECT_SIGNALS)]
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
    out = build_executive_rule_output(
        current_zone=current_zone,
        previous_zone=None,
        comparison_allowed=False,
    )
    action_keys = [m.phrase_key for m in out.actions]
    action_texts = [m.body for m in out.actions]
    warning_keys = {m.phrase_key for m in out.lines_for_section(SECT_RISKS)}
    assert "ssl_mode_full" in warning_keys
    assert "https_enforcement" in action_keys
    assert "dnssec" in action_keys
    assert "ssl_mode_full" in action_keys
    assert "waf" in action_keys
    assert "apex_proxy" in action_keys
    assert "cert_expire_30" in action_keys
    assert "audit_activity" in action_keys
    assert "Enable Always Use HTTPS - redirects HTTP to HTTPS for all traffic." in action_texts
    assert "Enable DNSSEC - prevents DNS spoofing and domain hijacking." in action_texts
    assert (
        "Upgrade TLS/SSL mode from Full to Full (Strict) - enables CA certificate validation."
        in action_texts
    )
    assert "Review Web Application Firewall (WAF) and rate-limiting baseline." in action_texts
    assert "Enable proxy on apex A/AAAA record - hides origin IP." in action_texts
    assert "Renew TLS certificate before expiry - prevents outages." in action_texts
    assert "Review audit log - check for unauthorized changes." in action_texts


def test_all_action_phrase_keys_are_reachable_by_rules():
    flex_zone = {
        "zone_name": "example.com",
        "zone_health": {
            "always_https": "off",
            "dnssec_status": "disabled",
            "ssl_mode": "flexible",
            "security_level": "off",
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
    full_zone = {
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
    keys_flex = {
        m.phrase_key
        for m in build_executive_rule_output(
            current_zone=flex_zone, previous_zone=None, comparison_allowed=False
        ).actions
    }
    keys_full = {
        m.phrase_key
        for m in build_executive_rule_output(
            current_zone=full_zone, previous_zone=None, comparison_allowed=False
        ).actions
    }
    expected = {
        "https_enforcement",
        "dnssec",
        "ssl_mode_flexible",
        "ssl_mode_full",
        "waf",
        "apex_proxy",
        "cert_expire_30",
        "audit_activity",
        "security_level_off",
    }
    assert keys_flex | keys_full == expected


def test_https_gap_action_not_enable_when_always_https_on() -> None:
    """Always HTTPS on but encrypted share below threshold: not the enable-setting action."""
    enc = 93  # 7% gap, above 5% threshold
    zone = {
        "zone_name": "example.com",
        "zone_health": {
            "always_https": "on",
            "dnssec_status": "active",
            "ssl_mode": "strict",
            "security_rules_active": 1,
        },
        "http": {"total_requests": 100, "encrypted_requests": enc},
        "security": {},
        "cache": {},
        "http_adaptive": {},
        "dns_records": {"apex_unproxied_a_aaaa": 0},
        "audit": {"total_events": 0},
        "certificates": {"total_certificate_packs": 1, "expiring_in_30_days": 0},
    }
    keys = {
        m.phrase_key
        for m in build_executive_rule_output(
            current_zone=zone, previous_zone=None, comparison_allowed=False
        ).actions
    }
    assert "https_enforcement" not in keys
    assert "https_encryption_gap" in keys


def _zone_minimal_for_security_level(*, security_level: str, ssl_mode: str = "strict") -> dict:
    return {
        "zone_name": "example.com",
        "zone_health": {
            "always_https": "on",
            "dnssec_status": "active",
            "ssl_mode": ssl_mode,
            "security_level": security_level,
            "ddos_protection": "on",
            "security_rules_active": 1,
        },
        "http": {"total_requests": 10, "encrypted_requests": 10},
        "security": {},
        "cache": {},
        "http_adaptive": {},
        "dns_records": {"apex_unproxied_a_aaaa": 0},
        "audit": {"total_events": 0},
        "certificates": {"total_certificate_packs": 1, "expiring_in_30_days": 0},
    }


def test_security_level_medium_no_low_high_under_attack_correlations() -> None:
    out = build_executive_rule_output(
        current_zone=_zone_minimal_for_security_level(security_level="medium"),
        previous_zone=None,
        comparison_allowed=False,
    )
    ckeys = {m.phrase_key for m in out.lines_for_section(SECT_SIGNALS)}
    assert "security_level_low" not in ckeys
    assert "security_level_high" not in ckeys
    assert "security_level_under_attack" not in ckeys


def test_security_level_low_info_correlation() -> None:
    out = build_executive_rule_output(
        current_zone=_zone_minimal_for_security_level(security_level="low"),
        previous_zone=None,
        comparison_allowed=False,
    )
    corr = {m.phrase_key: m.severity for m in out.lines_for_section(SECT_SIGNALS)}
    assert corr.get("security_level_low") == "info"


def test_security_level_high_info_correlation() -> None:
    out = build_executive_rule_output(
        current_zone=_zone_minimal_for_security_level(security_level="high"),
        previous_zone=None,
        comparison_allowed=False,
    )
    corr = {m.phrase_key: m.severity for m in out.lines_for_section(SECT_SIGNALS)}
    assert corr.get("security_level_high") == "info"


def test_security_level_off_warns_and_action() -> None:
    out = build_executive_rule_output(
        current_zone=_zone_minimal_for_security_level(security_level="off"),
        previous_zone=None,
        comparison_allowed=False,
    )
    wkeys = {m.phrase_key for m in out.lines_for_section(SECT_RISKS)}
    assert "security_level_off" in wkeys
    assert "security_level_off" in {m.phrase_key for m in out.actions}


def test_security_level_essentially_off_warns_and_action() -> None:
    out = build_executive_rule_output(
        current_zone=_zone_minimal_for_security_level(security_level="essentially_off"),
        previous_zone=None,
        comparison_allowed=False,
    )
    wkeys = {m.phrase_key for m in out.lines_for_section(SECT_RISKS)}
    assert "security_level_off" in wkeys
    assert "security_level_off" in {m.phrase_key for m in out.actions}


def test_security_level_under_attack_info_correlation() -> None:
    out = build_executive_rule_output(
        current_zone=_zone_minimal_for_security_level(security_level="under_attack"),
        previous_zone=None,
        comparison_allowed=False,
    )
    corr = {m.phrase_key: m.severity for m in out.lines_for_section(SECT_SIGNALS)}
    assert corr.get("security_level_under_attack") == "info"


def test_ignore_messages_filters_exact_key() -> None:
    current_zone = {
        "zone_name": "example.com",
        "zone_health": {
            "always_https": "off",
            "dnssec_status": "disabled",
            "ssl_mode": "strict",
            "security_rules_active": 1,
        },
        "http": {"total_requests": 100, "encrypted_requests": 100},
        "security": {},
        "cache": {},
        "http_adaptive": {},
        "dns_records": {"apex_unproxied_a_aaaa": 0},
        "audit": {"total_events": 0},
        "certificates": {},
    }
    filt = ExecutiveMessageFilter.from_entries(["dnssec"])
    out = build_executive_rule_output(
        current_zone=current_zone,
        previous_zone=None,
        comparison_allowed=False,
        message_filter=filt,
    )
    assert "dnssec" not in {m.phrase_key for m in out.actions}


def test_exec_msg_rejects_invalid_severity() -> None:
    try:
        exec_msg("bogus", "cert_expire_14", state="risk", section=SECT_RISKS, days=1)
        raise AssertionError("expected ValueError")
    except ValueError as e:
        assert "bogus" in str(e)


def test_format_line_with_severity_prefix() -> None:
    assert format_line_with_severity_prefix("warning", "TLS-001", "Hello") == "[!] [TLS-001] Hello"


def test_min_tls_version_weak_takeaway() -> None:
    zone = {
        "zone_name": "example.com",
        "zone_health": {
            "always_https": "on",
            "dnssec_status": "active",
            "ssl_mode": "strict",
            "security_level": "medium",
            "ddos_protection": "on",
            "security_rules_active": 1,
            "min_tls_version": "1.1",
            "tls_1_3": "on",
            "browser_check": "on",
            "email_obfuscation": "on",
            "opportunistic_encryption": "on",
        },
        "http": {"total_requests": 10, "encrypted_requests": 10},
        "security": {},
        "cache": {},
        "http_adaptive": {},
        "dns_records": {"apex_unproxied_a_aaaa": 0},
        "audit": {"total_events": 0},
        "certificates": {"total_certificate_packs": 1, "expiring_in_30_days": 0},
    }
    out = build_executive_rule_output(
        current_zone=zone, previous_zone=None, comparison_allowed=False
    )
    keys = {ln.phrase_key for ln in out.lines_for_section("risks")}
    assert "min_tls_version" in keys


def test_phrases_include_metadata_fields() -> None:
    """Every phrase entry must carry id/service/nist and at least one state dict."""
    from cloudflare_executive_report.executive.phrase_catalog import RULE_CATALOG

    for key, entry in RULE_CATALOG.items():
        assert isinstance(entry, dict), f"RULE_CATALOG[{key!r}] must be a dict"
        assert "id" in entry, key
        assert "service" in entry, key
        assert "nist" in entry, key
        assert isinstance(entry["nist"], list), key
        has_state = any(
            isinstance(entry.get(state), dict)
            for state in ("risk", "win", "action", "comparison", "observation")
        )
        assert has_state, key


def test_executive_message_filter_regex() -> None:
    filt = ExecutiveMessageFilter.from_entries([r"^ssl_"])
    assert filt.is_ignored("ssl_mode_off")
    assert not filt.is_ignored("dnssec")
