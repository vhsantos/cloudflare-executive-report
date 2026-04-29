"""Approved phrase catalog for CTO takeaways.

All wording in this file is sourced from the cto-resume-v2 guide.
Do not invent phrasing outside these templates.

Phrase keys are short identifiers (no severity or category prefix). Severity is stored
on :class:`~cloudflare_executive_report.executive.rules.ExecutiveLine` and combined with
the rendered body using :func:`format_line_with_severity_prefix`.

Each entry holds the display template plus check id, service label, and optional NIST
SP 800-53 controls (single source of truth for new rules).
"""

from __future__ import annotations

from typing import Any, TypedDict, cast


class PhraseStateEntry(TypedDict, total=False):
    """One phrase variant for a specific state."""

    text: str
    weight: int


class PhraseEntry(TypedDict, total=False):
    """One logical control with optional state variants."""

    id: str
    service: str
    nist: list[str]
    risk: PhraseStateEntry
    win: PhraseStateEntry
    action: PhraseStateEntry
    comparison: PhraseStateEntry
    observation: PhraseStateEntry


RULE_CATALOG: dict[str, PhraseEntry] = {
    "comparison_baseline": {
        "id": "CMP-001",
        "service": "Comparison",
        "nist": ["SI-4"],
        "comparison": {"text": "Comparing to: {start} to {end}"},
    },
    "comparison_first_report": {
        "id": "CMP-002",
        "service": "Comparison",
        "nist": ["SI-4"],
        "comparison": {"text": "First report for this zone - no prior data for comparison"},
    },
    "comparison_period_mismatch": {
        "id": "CMP-003",
        "service": "Comparison",
        "nist": ["SI-4"],
        "comparison": {
            "text": "Comparison skipped: previous period ({previous_days}d) differs from current ({current_days}d)"
        },
    },
    "comparison_missing_streams": {
        "id": "CMP-004",
        "service": "Comparison",
        "nist": ["SI-4"],
        "comparison": {
            "text": "Comparison incomplete: some data streams unavailable in previous report"
        },
    },
    "traffic_up": {
        "id": "CMP-005",
        "service": "Traffic",
        "nist": ["SI-4"],
        "win": {"text": "Traffic up {pct}% - business growing"},
        "comparison": {"text": "Traffic growth: {pct}% increase from previous period"},
    },
    "traffic_down": {
        "id": "CMP-006",
        "service": "Traffic",
        "nist": ["SI-4"],
        "comparison": {"text": "Traffic decline: {pct}% decrease from previous period"},
    },
    "latency_delta": {
        "id": "CMP-007",
        "service": "Performance",
        "nist": ["SI-4"],
        "win": {"text": "Response time improved by {ms}ms - faster user experience"},
        "comparison": {"text": "Performance degraded: response time increased by {ms}ms"},
    },
    "ssl_mode_transition_regression": {
        "id": "CMP-008",
        "service": "SSL/TLS",
        "nist": ["SC-8"],
        "comparison": {
            "text": "Security regression: SSL mode changed from {previous} to {current}"
        },
    },
    "threats_vs_traffic_flat": {
        "id": "CMP-009",
        "service": "Security",
        "nist": ["SI-4"],
        "comparison": {"text": "Possible targeted attack: threats up {pct}% with stable traffic"},
    },
    "threats_vs_traffic_up": {
        "id": "CMP-010",
        "service": "Security",
        "nist": ["SI-4"],
        "comparison": {"text": "Attack volume increasing: threats up {pct}% alongside traffic"},
    },
    "missing_data_warning": {
        "id": "CMP-011",
        "service": "Data Quality",
        "nist": ["SI-4"],
        "observation": {
            "text": "Missing data for {warning_count} metrics - verdict may be affected."
        },
    },
    "apex_proxy": {
        "id": "APEX-001",
        "service": "DNS",
        "nist": ["SC-7", "SC-20"],
        "risk": {"text": "Apex record not proxied - origin IP exposed to attackers", "weight": 7},
        "win": {"text": "Apex record now proxied - origin IP protected"},
        "action": {"text": "Enable proxy on apex A/AAAA record - hides origin IP."},
        "comparison": {"text": "Security regression: apex changed from {previous} to {current}"},
    },
    "dnssec": {
        "id": "DNS-001",
        "service": "DNS",
        "nist": ["SC-20"],
        "risk": {"text": "DNSSEC disabled - domain spoofing risk", "weight": 7},
        "win": {"text": "DNSSEC now active - spoofing protection enabled"},
        "action": {"text": "Enable DNSSEC - prevents DNS spoofing and domain hijacking."},
    },
    "dns_only_with_proxied_records": {
        "id": "DNS-002",
        "service": "DNS",
        "nist": [],
        "observation": {
            "text": "DNS-only report shows HTTP warnings because your zone has proxied DNS records that route traffic through Cloudflare's edge."
        },
    },
    "cert_expire_14": {
        "id": "CERT-001",
        "service": "Certificates",
        "nist": ["SC-12", "SC-13"],
        "risk": {"text": "Certificate expires in {days} days - renew immediately", "weight": 10},
        "action": {"text": "Renew TLS certificate before expiry - prevents outages."},
    },
    "cert_expire_30": {
        "id": "CERT-002",
        "service": "Certificates",
        "nist": ["SC-12", "SC-13"],
        "risk": {"text": "Certificate expires in {days} days - schedule renewal", "weight": 7},
        "action": {"text": "Renew TLS certificate before expiry - prevents outages."},
    },
    "cert_presence": {
        "id": "CERT-003",
        "service": "Certificates",
        "nist": ["SC-8", "SC-12"],
        "risk": {"text": "No SSL certificate deployed - traffic not encrypted", "weight": 6},
    },
    "ssl_mode_off": {
        "id": "TLS-001",
        "service": "SSL/TLS",
        "nist": ["SC-8", "SC-13"],
        "risk": {"text": "TLS/SSL mode Off - enable HTTPS immediately.", "weight": 10},
        "action": {
            "text": "Change SSL/TLS mode to Full (Strict) for end-to-end encryption with certificate validation."
        },
    },
    "ssl_mode_flexible": {
        "id": "TLS-002",
        "service": "SSL/TLS",
        "nist": ["SC-8", "SC-13"],
        "risk": {
            "text": "TLS/SSL mode Flexible (HTTP may reach origin) - move to Full (Strict) now.",
            "weight": 10,
        },
        "action": {
            "text": "Change SSL/TLS mode to Full (Strict) for end-to-end encryption with certificate validation."
        },
        "observation": {
            "text": "Flexible mode allows HTTP to origin - verify this matches your security requirements."
        },
    },
    "ssl_mode_full": {
        "id": "TLS-003",
        "service": "SSL/TLS",
        "nist": ["SC-8", "SC-13"],
        "risk": {
            "text": "TLS/SSL mode Full without CA-validated origin certificate - upgrade to Full (Strict).",
            "weight": 8,
        },
        "action": {
            "text": "Upgrade TLS/SSL mode from Full to Full (Strict) - enables CA certificate validation."
        },
        "win": {"text": "Encryption upgraded to Full/Strict - security improved"},
    },
    "min_tls_version": {
        "id": "TLS-004",
        "service": "SSL/TLS",
        "nist": ["SC-8", "SC-13"],
        "risk": {
            "text": "Minimum TLS version is {version} at edge - raise to at least 1.2 immediately.",
            "weight": 9,
        },
        "observation": {
            "text": "Minimum TLS version is 1.2. Evaluate TLS 1.3 adoption when client compatibility allows."
        },
    },
    "tls_1_3": {
        "id": "TLS-005",
        "service": "SSL/TLS",
        "nist": ["SC-8", "SC-13"],
        "risk": {
            "text": "TLS 1.3 is not enabled at edge - enable for stronger defaults.",
            "weight": 5,
        },
    },
    "hsts": {
        "id": "TLS-006",
        "service": "SSL/TLS",
        "nist": ["SC-8", "SC-13"],
        "risk": {
            "text": "HSTS disabled - HTTPS not enforced. Visitors may connect over insecure HTTP.",
            "weight": 8,
        },
        "observation": {"text": "HSTS enabled but configuration is suboptimal: {issues}."},
    },
    "https_enforcement": {
        "id": "TLS-007",
        "service": "SSL/TLS",
        "nist": ["SC-8"],
        "action": {"text": "Enable Always Use HTTPS - redirects HTTP to HTTPS for all traffic."},
    },
    "https_encryption_gap": {
        "id": "TLS-008",
        "service": "SSL/TLS",
        "nist": ["SC-8", "SI-4"],
        "action": {
            "text": "About {gap_pct}% of requests are not encrypted at edge while Always Use HTTPS is on - review plain HTTP, redirects, Page Rules, and mixed content."
        },
    },
    "opportunistic_encryption": {
        "id": "TLS-009",
        "service": "SSL/TLS",
        "nist": ["SC-8"],
        "observation": {
            "text": "Opportunistic Encryption is off - optional edge HTTPS hint for HTTP clients."
        },
    },
    "waf": {
        "id": "WAF-001",
        "service": "WAF",
        "nist": ["SI-3", "SI-4"],
        "risk": {"text": "Web Application Firewall disabled - no attack protection", "weight": 9},
        "action": {"text": "Review Web Application Firewall (WAF) and rate-limiting baseline."},
    },
    "ddos_protection": {
        "id": "SEC-001",
        "service": "Security",
        "nist": ["SC-7", "SI-4"],
        "risk": {"text": "DDoS protection disabled - availability at risk", "weight": 9},
    },
    "security_level_off": {
        "id": "SEC-002",
        "service": "Security Level",
        "nist": ["SI-4", "CM-6"],
        "risk": {
            "text": "Cloudflare Security Level is off or essentially off - known threats are barely challenged.",
            "weight": 10,
        },
        "action": {
            "text": "Enable Cloudflare automatic Security Level (Security app) - avoid off or essentially off."
        },
    },
    "security_level_low": {
        "id": "SEC-003",
        "service": "Security Level",
        "nist": ["SI-4", "CM-6"],
        "observation": {
            "text": "Security Level is Low. Default or automatic level provides stronger protection."
        },
    },
    "security_level_high": {
        "id": "SEC-004",
        "service": "Security Level",
        "nist": ["SI-4", "CM-6"],
        "observation": {
            "text": "Security Level is High - watch for false positives blocking legitimate users."
        },
    },
    "security_level_under_attack": {
        "id": "SEC-005",
        "service": "Security Level",
        "nist": ["SI-4"],
        "observation": {
            "text": "Cloudflare Under Attack mode is on - confirm this is intentional and temporary."
        },
    },
    "browser_integrity": {
        "id": "SEC-006",
        "service": "Security",
        "nist": ["SI-3", "SI-4"],
        "risk": {
            "text": "Browser Integrity Check is off - consider enabling to reduce automated abuse.",
            "weight": 6,
        },
    },
    "email_obfuscation": {
        "id": "SEC-007",
        "service": "Scraping",
        "nist": ["SC-18"],
        "observation": {
            "text": "Email obfuscation is off. Enable to reduce email address harvesting."
        },
    },
    "origin_health": {
        "id": "COR-001",
        "service": "Reliability",
        "nist": ["SI-4"],
        "observation": {
            "text": "Origin overloaded: high error rate ({err_pct}%) with slow response ({latency_ms}ms)"
        },
    },
    "cache_efficiency": {
        "id": "COR-002",
        "service": "Performance",
        "nist": ["CM-6"],
        "observation": {
            "text": "Caching inefficient: {cache_hit}% hit rate with {bandwidth_gb}GB bandwidth - cost impact"
        },
        "comparison": {"text": "Cache efficiency dropped: {pp}% decrease - review caching rules"},
    },
    "apex_ddos_alignment": {
        "id": "COR-003",
        "service": "DNS",
        "nist": ["SC-7", "SI-4"],
        "observation": {
            "text": "Origin exposed: apex not proxied, but DDoS protection requires proxy"
        },
    },
    "threat_activity": {
        "id": "COR-004",
        "service": "Security",
        "nist": ["SI-4"],
        "observation": {
            "text": "Active attack: {mitigation_pct}% of requests mitigated - WAF blocking threats"
        },
    },
    "audit_activity": {
        "id": "COR-005",
        "service": "Audit",
        "nist": ["AU-2", "SI-4"],
        "observation": {
            "text": "Unusual activity: {events} audit events in period - review if expected"
        },
        "action": {"text": "Review audit log - check for unauthorized changes."},
    },
    "origin_errors_high": {
        "id": "COR-006",
        "service": "Reliability",
        "nist": ["SI-4"],
        "observation": {"text": "5xx error rate is {err_pct}% - investigate immediately."},
    },
    "email_dmarc_none": {
        "id": "EMAIL-001",
        "service": "Email",
        "nist": ["SI-7", "SC-7"],
        "risk": {
            "text": "DMARC policy is None. Attackers can send email as your domain.",
            "weight": 10,
        },
        "action": {"text": "Set DMARC policy to quarantine, monitor reports, then move to reject."},
    },
    "email_dmarc_quarantine": {
        "id": "EMAIL-002",
        "service": "Email",
        "nist": ["SI-7", "SC-7"],
        "risk": {
            "text": "DMARC policy is Quarantine. Suspicious emails go to spam but are not fully blocked.",
            "weight": 3,
        },
        "action": {"text": "Upgrade DMARC policy to reject after verifying legitimate senders."},
    },
    "email_dmarc_reject": {
        "id": "EMAIL-003",
        "service": "Email",
        "nist": ["SI-7", "SC-7"],
        "win": {"text": "DMARC policy upgraded from {previous} to Reject. Spoofing blocked."},
    },
    "email_spf_missing": {
        "id": "EMAIL-004",
        "service": "Email",
        "nist": ["SI-7", "SC-7"],
        "risk": {
            "text": "SPF record missing. Unauthorized senders can spoof domain",
            "weight": 8,
        },
        "action": {
            "text": "Add an SPF TXT record. Start with ~all, then move to -all after verification."
        },
    },
    "email_spf_softfail": {
        "id": "EMAIL-005",
        "service": "Email",
        "nist": ["SI-7", "SC-7"],
        "observation": {"text": "SPF is Soft Fail (~all). Unauthorized senders not fully blocked"},
        "action": {"text": "Move to hard fail (-all) after verifying all legitimate senders."},
    },
    "email_spf_hardfail": {
        "id": "EMAIL-006",
        "service": "Email",
        "nist": ["SI-7", "SC-7"],
        "win": {
            "text": "SPF policy hardened from {previous} to Hard Fail. Domain spoofing blocked."
        },
    },
    "email_dkim_missing": {
        "id": "EMAIL-007",
        "service": "Email",
        "nist": ["SI-7"],
        "risk": {
            "text": "DKIM missing. Outbound email authenticity cannot be verified.",
            "weight": 8,
        },
        "action": {"text": "Enable DKIM signing to ensure message integrity."},
    },
    "email_dkim_configured": {
        "id": "EMAIL-008",
        "service": "Email",
        "nist": ["SI-7"],
        "win": {"text": "DKIM now is properly configured. Emails authenticity verified"},
    },
    "email_dkim_selector_problem": {
        "id": "EMAIL-009",
        "service": "Email",
        "nist": ["SI-7", "AU-6"],
        "risk": {
            "text": "DKIM selectors not rotated. Long-lived keys increase risk.",
            "weight": 3,
        },
        "action": {
            "text": "Rotate DKIM keys frequently (every 6-12 months) and remove expired selectors."
        },
    },
    "email_high_fail_rate": {
        "id": "EMAIL-010",
        "service": "Email",
        "nist": ["AU-6", "SI-4"],
        "observation": {"text": "High DMARC fail rate: {fail_pct}%. Review unauthorized senders"},
    },
    "email_routing_drops": {
        "id": "EMAIL-011",
        "service": "Email",
        "nist": ["SI-4"],
        "observation": {"text": "Email routing dropped {dropped} messages. Review routing rules"},
    },
}

PREFIXES: dict[str, str] = {
    "positive": "[OK]",
    "info": "[i]",
    "warning": "[!]",
    "critical": "[!!]",
}


def get_phrase(phrase_key: str, state: str) -> dict[str, Any]:
    """Return phrase payload for one phrase key and explicit state."""
    entry = RULE_CATALOG[phrase_key]
    state_entry = cast(dict[str, Any], entry).get(state)
    if not isinstance(state_entry, dict):
        raise TypeError(f"State {state!r} for phrase key {phrase_key!r} must be a dict")
    text = state_entry.get("text")
    if not isinstance(text, str) or not text.strip():
        raise ValueError(f"Missing text for phrase key {phrase_key!r} state {state!r}")
    if state not in ("risk", "win", "action", "comparison", "observation"):
        raise ValueError(f"Invalid phrase state {state!r}")
    if state != "risk":
        weight = 0
    else:
        raw_weight = state_entry.get("weight")
        if not isinstance(raw_weight, int) or not (1 <= raw_weight <= 10):
            raise ValueError(f"RULE_CATALOG[{phrase_key!r}].{state}.weight must be integer 1..10")
        weight = raw_weight
    return {
        "text": text,
        "weight": weight,
        "id": entry["id"],
        "service": entry["service"],
        "nist": entry["nist"],
    }


def format_line_with_severity_prefix(severity: str, check_id: str, body: str) -> str:
    """Return one executive line: severity marker, bracketed check id, then body."""
    return f"{PREFIXES[severity]} [{check_id}] {body}"
