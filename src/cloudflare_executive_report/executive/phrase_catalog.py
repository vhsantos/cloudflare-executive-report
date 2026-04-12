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

from dataclasses import dataclass
from typing import TypedDict


class PhraseEntry(TypedDict):
    """One phrase template plus check metadata for JSON/PDF."""

    text: str
    id: str
    service: str
    nist: list[str]
    weight: int


@dataclass(frozen=True, slots=True)
class PhraseMeta:
    """Stable check id, service name, and optional NIST controls for one phrase key."""

    check_id: str
    service: str
    nist: tuple[str, ...]


_DEFAULT_META = PhraseMeta(check_id="GEN-000", service="General", nist=())

RULE_CATALOG: dict[str, PhraseEntry] = {
    "baseline_reference": {
        "text": "Comparing to: {start} to {end}",
        "id": "CMP-001",
        "service": "Comparison",
        "nist": ["SI-4"],
        "weight": 3,
    },
    "no_comparison_first_report": {
        "text": "First report for this zone - no prior data for comparison",
        "id": "CMP-002",
        "service": "Comparison",
        "nist": ["SI-4"],
        "weight": 3,
    },
    "no_comparison_period_mismatch": {
        "text": "Comparison skipped: previous period ({previous_days}d) differs from current ({current_days}d)",
        "id": "CMP-003",
        "service": "Comparison",
        "nist": ["SI-4"],
        "weight": 3,
    },
    "no_comparison_missing_streams": {
        "text": "Comparison incomplete: some data streams unavailable in previous report",
        "id": "CMP-004",
        "service": "Comparison",
        "nist": ["SI-4"],
        "weight": 3,
    },
    "traffic_up_positive": {
        "text": "Traffic up {pct}% - business growing",
        "id": "CMP-010",
        "service": "Traffic",
        "nist": ["SI-4"],
        "weight": 4,
    },
    "latency_down": {
        "text": "Response time improved by {ms}ms - faster user experience",
        "id": "CMP-011",
        "service": "Performance",
        "nist": ["SI-4"],
        "weight": 4,
    },
    "apex_proxied": {
        "text": "Apex record now proxied - origin IP protected",
        "id": "APEX-001",
        "service": "DNS",
        "nist": ["SC-7", "SC-20"],
        "weight": 4,
    },
    "ssl_upgraded": {
        "text": "Encryption upgraded to Full/Strict - security improved",
        "id": "TLS-010",
        "service": "SSL/TLS",
        "nist": ["SC-8", "SC-13"],
        "weight": 4,
    },
    "dnssec_enabled": {
        "text": "DNSSEC now active - spoofing protection enabled",
        "id": "DNS-010",
        "service": "DNS",
        "nist": ["SC-20"],
        "weight": 4,
    },
    "apex_unproxied": {
        "text": "Apex record not proxied - origin IP exposed to attackers",
        "id": "APEX-002",
        "service": "DNS",
        "nist": ["SC-7", "SC-20"],
        "weight": 7,
    },
    "cert_14": {
        "text": "Certificate expires in {days} days - renew immediately",
        "id": "CERT-001",
        "service": "Certificates",
        "nist": ["SC-12", "SC-13"],
        "weight": 10,
    },
    "cert_30": {
        "text": "Certificate expires in {days} days - schedule renewal",
        "id": "CERT-002",
        "service": "Certificates",
        "nist": ["SC-12", "SC-13"],
        "weight": 9,
    },
    "ssl_off": {
        "text": "TLS/SSL mode Off - enable HTTPS immediately.",
        "id": "TLS-001",
        "service": "SSL/TLS",
        "nist": ["SC-8", "SC-13"],
        "weight": 10,
    },
    "ssl_flexible": {
        "text": "TLS/SSL mode Flexible (HTTP may reach origin) - move to Full (Strict) now.",
        "id": "TLS-002",
        "service": "SSL/TLS",
        "nist": ["SC-8", "SC-13"],
        "weight": 10,
    },
    "ssl_full": {
        "text": "TLS/SSL mode Full without CA-validated origin certificate - upgrade to Full (Strict).",
        "id": "TLS-003",
        "service": "SSL/TLS",
        "nist": ["SC-8", "SC-13"],
        "weight": 8,
    },
    "dnssec_off": {
        "text": "DNSSEC disabled - domain spoofing risk",
        "id": "DNS-001",
        "service": "DNS",
        "nist": ["SC-20"],
        "weight": 7,
    },
    "waf_off": {
        "text": "Web Application Firewall disabled - no attack protection",
        "id": "WAF-001",
        "service": "WAF",
        "nist": ["SI-3", "SI-4"],
        "weight": 9,
    },
    "ddos_off": {
        "text": "DDoS protection disabled - availability at risk",
        "id": "SEC-001",
        "service": "Security",
        "nist": ["SC-7", "SI-4"],
        "weight": 9,
    },
    "no_cert_packs": {
        "text": "No SSL certificate deployed - traffic not encrypted",
        "id": "CERT-003",
        "service": "Certificates",
        "nist": ["SC-8", "SC-12"],
        "weight": 6,
    },
    "security_level_off_or_minimal": {
        "text": "Cloudflare Security Level is off or essentially off - known threats are barely challenged.",
        "id": "SEC-010",
        "service": "Security Level",
        "nist": ["SI-4", "CM-6"],
        "weight": 10,
    },
    "origin_overloaded": {
        "text": "Origin overloaded: high error rate ({err_pct}%) with slow response ({latency_ms}ms)",
        "id": "COR-001",
        "service": "Reliability",
        "nist": ["SI-4"],
        "weight": 9,
    },
    "cache_inefficient": {
        "text": "Caching inefficient: {cache_hit}% hit rate with {bandwidth_gb}GB bandwidth - cost impact",
        "id": "COR-002",
        "service": "Performance",
        "nist": ["CM-6"],
        "weight": 7,
    },
    "apex_ddos_mismatch": {
        "text": "Origin exposed: apex not proxied, but DDoS protection requires proxy",
        "id": "COR-003",
        "service": "DNS",
        "nist": ["SC-7", "SI-4"],
        "weight": 7,
    },
    "ssl_flexible_with_cert": {
        "text": "Encryption weak: Flexible mode allows HTTP - upgrade to Full/Strict",
        "id": "COR-004",
        "service": "SSL/TLS",
        "nist": ["SC-8"],
        "weight": 7,
    },
    "threats_high": {
        "text": "Active attack: {mitigation_pct}% of requests mitigated - WAF blocking threats",
        "id": "COR-005",
        "service": "Security",
        "nist": ["SI-4"],
        "weight": 7,
    },
    "audit_high": {
        "text": "Unusual activity: {events} audit events in period - review if expected",
        "id": "COR-006",
        "service": "Audit",
        "nist": ["AU-2", "SI-4"],
        "weight": 6,
    },
    "security_under_attack_mode": {
        "text": "Cloudflare Under Attack mode is on - confirm this is intentional and temporary.",
        "id": "SEC-011",
        "service": "Security Level",
        "nist": ["SI-4"],
        "weight": 5,
    },
    "security_level_low": {
        "text": "Security Level is Low - consider default or automatic for stronger baseline protection.",
        "id": "SEC-012",
        "service": "Security Level",
        "nist": ["SI-4", "CM-6"],
        "weight": 5,
    },
    "security_level_high": {
        "text": "Security Level is High - watch for false positives blocking legitimate users.",
        "id": "SEC-013",
        "service": "Security Level",
        "nist": ["SI-4", "CM-6"],
        "weight": 5,
    },
    "threats_up_traffic_flat": {
        "text": "Possible targeted attack: threats up {pct}% with stable traffic",
        "id": "CMP-020",
        "service": "Security",
        "nist": ["SI-4"],
        "weight": 9,
    },
    "threats_up_traffic_up": {
        "text": "Attack volume increasing: threats up {pct}% alongside traffic",
        "id": "CMP-021",
        "service": "Security",
        "nist": ["SI-4"],
        "weight": 7,
    },
    "traffic_up_comparison": {
        "text": "Traffic growth: {pct}% increase from previous period",
        "id": "CMP-022",
        "service": "Traffic",
        "nist": ["SI-4"],
        "weight": 4,
    },
    "traffic_down_comparison": {
        "text": "Traffic decline: {pct}% decrease from previous period",
        "id": "CMP-023",
        "service": "Traffic",
        "nist": ["SI-4"],
        "weight": 7,
    },
    "latency_up_comparison": {
        "text": "Performance degraded: response time increased by {ms}ms",
        "id": "CMP-024",
        "service": "Performance",
        "nist": ["SI-4"],
        "weight": 7,
    },
    "cache_hit_down": {
        "text": "Cache efficiency dropped: {pp}% decrease - review caching rules",
        "id": "CMP-025",
        "service": "Cache",
        "nist": ["CM-6"],
        "weight": 7,
    },
    "apex_regression": {
        "text": "Security regression: apex changed from {previous} to {current}",
        "id": "CMP-026",
        "service": "DNS",
        "nist": ["SC-7"],
        "weight": 9,
    },
    "ssl_regression": {
        "text": "Security regression: SSL mode changed from {previous} to {current}",
        "id": "CMP-027",
        "service": "SSL/TLS",
        "nist": ["SC-8"],
        "weight": 9,
    },
    "enable_always_https": {
        "text": "Enable Always Use HTTPS - redirects HTTP to HTTPS for all traffic.",
        "id": "ACT-001",
        "service": "SSL/TLS",
        "nist": ["SC-8"],
        "weight": 5,
    },
    "review_https_encryption_gap": {
        "text": "About {gap_pct}% of requests are not encrypted at edge while Always Use HTTPS is on - review plain HTTP, redirects, Page Rules, and mixed content.",
        "id": "ACT-002",
        "service": "SSL/TLS",
        "nist": ["SC-8", "SI-4"],
        "weight": 5,
    },
    "review_dnssec": {
        "text": "Enable DNSSEC - prevents DNS spoofing and domain hijacking.",
        "id": "DNS-002",
        "service": "DNS",
        "nist": ["SC-20"],
        "weight": 5,
    },
    "review_ssl_mode": {
        "text": "Change SSL/TLS mode to Full (Strict) for end-to-end encryption with certificate validation.",
        "id": "ACT-003",
        "service": "SSL/TLS",
        "nist": ["SC-8", "CM-6"],
        "weight": 5,
    },
    "ssl_upgrade_full_to_strict": {
        "text": "Upgrade TLS/SSL mode from Full to Full (Strict) - enables CA certificate validation.",
        "id": "ACT-004",
        "service": "SSL/TLS",
        "nist": ["SC-8", "SC-13"],
        "weight": 5,
    },
    "review_waf_posture": {
        "text": "Review Web Application Firewall (WAF) and rate-limiting baseline.",
        "id": "WAF-002",
        "service": "WAF",
        "nist": ["SI-3", "SI-4"],
        "weight": 5,
    },
    "enable_apex_proxy": {
        "text": "Enable proxy on apex A/AAAA record - hides origin IP.",
        "id": "ACT-005",
        "service": "DNS",
        "nist": ["SC-7"],
        "weight": 5,
    },
    "plan_tls_renewal": {
        "text": "Renew TLS certificate before expiry - prevents outages.",
        "id": "ACT-006",
        "service": "Certificates",
        "nist": ["SC-12"],
        "weight": 5,
    },
    "review_audit_activity": {
        "text": "Review audit log - check for unauthorized changes.",
        "id": "ACT-007",
        "service": "Audit",
        "nist": ["AU-2"],
        "weight": 5,
    },
    "enable_cloudflare_security_level_auto": {
        "text": "Enable Cloudflare automatic Security Level (Security app) - avoid off or essentially off.",
        "id": "ACT-008",
        "service": "Security Level",
        "nist": ["CM-6", "SI-4"],
        "weight": 5,
    },
    "min_tls_version_weak": {
        "text": "Minimum TLS version is {version} at edge - raise to at least 1.2 immediately.",
        "id": "TLS-011",
        "service": "SSL/TLS",
        "nist": ["SC-8", "SC-13"],
        "weight": 9,
    },
    "min_tls_version_acceptable": {
        "text": "Minimum TLS version is 1.2 - consider 1.3 when client base allows.",
        "id": "TLS-012",
        "service": "SSL/TLS",
        "nist": ["SC-8"],
        "weight": 5,
    },
    "tls_1_3_disabled": {
        "text": "TLS 1.3 is not enabled at edge - enable for stronger defaults.",
        "id": "TLS-013",
        "service": "SSL/TLS",
        "nist": ["SC-8", "SC-13"],
        "weight": 5,
    },
    "hsts_disabled": {
        "text": (
            "HTTP Strict Transport Security (HSTS) is not enabled at the edge - enable it under "
            "SSL/TLS > Edge Certificates (adds Strict-Transport-Security beyond Always Use HTTPS alone)."
        ),
        "id": "TLS-015",
        "service": "SSL/TLS",
        "nist": ["SC-8", "SC-13"],
        "weight": 8,
    },
    "hsts_suboptimal": {
        "text": "HSTS is on but suboptimal: {issues}.",
        "id": "TLS-016",
        "service": "SSL/TLS",
        "nist": ["SC-8", "SC-13"],
        "weight": 4,
    },
    "browser_integrity_disabled": {
        "text": "Browser Integrity Check is off - consider enabling to reduce automated abuse.",
        "id": "SEC-014",
        "service": "Security",
        "nist": ["SI-3", "SI-4"],
        "weight": 6,
    },
    "email_obfuscation_disabled": {
        "text": "Email obfuscation is off - consider enabling to reduce address harvesting.",
        "id": "SEC-015",
        "service": "Scraping",
        "nist": ["SC-18"],
        "weight": 2,
    },
    "opportunistic_encryption_disabled": {
        "text": "Opportunistic Encryption is off - optional edge HTTPS hint for HTTP clients.",
        "id": "TLS-014",
        "service": "SSL/TLS",
        "nist": ["SC-8"],
        "weight": 1,
    },
}

PREFIXES: dict[str, str] = {
    "positive": "[OK]",
    "info": "[i]",
    "warning": "[!]",
    "critical": "[!!]",
}

_DEFAULT_SECURITY_POSTURE_WEIGHT: int = 5


def get_weight(phrase_key: str) -> int:
    """Return posture score weight (1-10) for ``phrase_key``."""
    entry = RULE_CATALOG.get(phrase_key)
    if entry is None:
        return _DEFAULT_SECURITY_POSTURE_WEIGHT
    raw = entry.get("weight", _DEFAULT_SECURITY_POSTURE_WEIGHT)
    if isinstance(raw, int) and 1 <= raw <= 10:
        return raw
    return _DEFAULT_SECURITY_POSTURE_WEIGHT


def format_line_with_severity_prefix(severity: str, check_id: str, body: str) -> str:
    """Return one executive line: severity marker, bracketed check id, then body."""
    return f"{PREFIXES[severity]} [{check_id}] {body}"


def render_phrase(key: str, **kwargs: object) -> str:
    """Format the template for ``key`` using ``kwargs``."""
    entry = RULE_CATALOG[key]
    template = entry["text"]
    assert isinstance(template, str)
    return template.format(**kwargs)


def get_phrase_meta(phrase_key: str) -> PhraseMeta:
    """Return metadata for ``phrase_key``, or a generic default if unregistered."""
    entry = RULE_CATALOG.get(phrase_key)
    if entry is None:
        return _DEFAULT_META
    nist_raw = entry.get("nist", [])
    if not isinstance(nist_raw, list):
        raise TypeError(f"phrase {phrase_key!r}: nist must be a list")
    return PhraseMeta(
        check_id=str(entry["id"]),
        service=str(entry["service"]),
        nist=tuple(str(x) for x in nist_raw),
    )
