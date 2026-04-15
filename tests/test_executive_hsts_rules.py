"""Tests for HSTS executive takeaways from ``zone_health.hsts``."""

from cloudflare_executive_report.common.constants import HSTS_RECOMMENDED_MAX_AGE_SECONDS
from cloudflare_executive_report.executive.rules import (
    SECT_RISKS,
    SECT_SIGNALS,
    build_executive_rule_output,
)


def _base_zone(*, zone_health: dict[str, object]) -> dict[str, object]:
    return {
        "zone_name": "example.com",
        "zone_health": zone_health,
        "http": {"total_requests": 10, "encrypted_requests": 10},
        "security": {},
        "cache": {},
        "http_adaptive": {},
        "dns_records": {"apex_unproxied_a_aaaa": 0},
        "audit": {"total_events": 0},
        "certificates": {"total_certificate_packs": 1, "expiring_in_30_days": 0},
    }


def test_hsts_disabled_when_always_https_on_and_hsts_off() -> None:
    zh = {
        "ssl_mode": "strict",
        "always_https": "on",
        "dnssec_status": "active",
        "security_level": "medium",
        "ddos_protection": "on",
        "security_rules_active": 1,
        "min_tls_version": "1.2",
        "tls_1_3": "on",
        "browser_check": "on",
        "email_obfuscation": "on",
        "opportunistic_encryption": "on",
        "hsts": {
            "available": True,
            "skipped": False,
            "enabled": False,
            "max_age": None,
            "include_subdomains": None,
            "preload": None,
        },
    }
    out = build_executive_rule_output(
        current_zone=_base_zone(zone_health=zh),
        previous_zone=None,
        comparison_allowed=False,
    )
    keys = {ln.phrase_key for ln in out.lines_for_section(SECT_RISKS)}
    assert "hsts" in keys


def test_hsts_no_line_when_always_https_off_even_if_hsts_disabled() -> None:
    zh = {
        "ssl_mode": "strict",
        "always_https": "off",
        "dnssec_status": "active",
        "security_level": "medium",
        "ddos_protection": "on",
        "security_rules_active": 1,
        "min_tls_version": "1.2",
        "tls_1_3": "on",
        "browser_check": "on",
        "email_obfuscation": "on",
        "opportunistic_encryption": "on",
        "hsts": {
            "available": True,
            "skipped": False,
            "enabled": False,
            "max_age": None,
            "include_subdomains": None,
            "preload": None,
        },
    }
    out = build_executive_rule_output(
        current_zone=_base_zone(zone_health=zh),
        previous_zone=None,
        comparison_allowed=False,
    )
    keys = {ln.phrase_key for ln in out.lines_for_section(SECT_RISKS)}
    assert "hsts" not in keys


def test_hsts_no_line_when_ssl_mode_off() -> None:
    zh = {
        "ssl_mode": "off",
        "always_https": "on",
        "dnssec_status": "active",
        "security_level": "medium",
        "ddos_protection": "on",
        "security_rules_active": 1,
        "hsts": {
            "available": True,
            "skipped": False,
            "enabled": False,
            "max_age": None,
            "include_subdomains": None,
            "preload": None,
        },
    }
    out = build_executive_rule_output(
        current_zone=_base_zone(zone_health=zh),
        previous_zone=None,
        comparison_allowed=False,
    )
    keys = {ln.phrase_key for ln in out.lines_for_section(SECT_RISKS)}
    assert "hsts" not in keys


def test_hsts_skipped_or_unavailable_emits_nothing() -> None:
    for hsts in (
        {"available": False, "skipped": True},
        {"available": False, "skipped": False},
    ):
        zh = {
            "ssl_mode": "strict",
            "always_https": "on",
            "dnssec_status": "active",
            "security_level": "medium",
            "ddos_protection": "on",
            "security_rules_active": 1,
            "min_tls_version": "1.2",
            "tls_1_3": "on",
            "browser_check": "on",
            "email_obfuscation": "on",
            "opportunistic_encryption": "on",
            "hsts": hsts,
        }
        out = build_executive_rule_output(
            current_zone=_base_zone(zone_health=zh),
            previous_zone=None,
            comparison_allowed=False,
        )
        keys = {ln.phrase_key for ln in out.lines_for_section(SECT_RISKS)}
        assert "hsts" not in keys


def test_hsts_suboptimal_low_max_age_and_no_include_subdomains() -> None:
    zh = {
        "ssl_mode": "strict",
        "always_https": "on",
        "dnssec_status": "active",
        "security_level": "medium",
        "ddos_protection": "on",
        "security_rules_active": 1,
        "min_tls_version": "1.2",
        "tls_1_3": "on",
        "browser_check": "on",
        "email_obfuscation": "on",
        "opportunistic_encryption": "on",
        "hsts": {
            "available": True,
            "skipped": False,
            "enabled": True,
            "max_age": 86400,
            "include_subdomains": False,
            "preload": False,
        },
    }
    out = build_executive_rule_output(
        current_zone=_base_zone(zone_health=zh),
        previous_zone=None,
        comparison_allowed=False,
    )
    sub = [ln for ln in out.lines_for_section(SECT_SIGNALS) if ln.phrase_key == "hsts"]
    assert len(sub) == 1
    body = sub[0].body
    assert "86400" in body
    assert str(HSTS_RECOMMENDED_MAX_AGE_SECONDS) in body
    assert "Include Subdomains" in body
