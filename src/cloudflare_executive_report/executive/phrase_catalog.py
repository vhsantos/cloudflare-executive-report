"""Approved phrase catalog for CTO takeaways.

All wording in this file is sourced from the cto-resume-v2 guide.
Do not invent phrasing outside these templates.

Phrase keys are short identifiers (no severity or category prefix). Severity is stored
on :class:`~cloudflare_executive_report.executive.rules.ExecutiveLine` and combined with
the rendered body using :func:`format_line_with_severity_prefix`.
"""

from __future__ import annotations

PHRASES: dict[str, str] = {
    "baseline_reference": "Comparing to: {start} to {end}",
    "no_comparison_first_report": "First report for this zone - no prior data for comparison",
    "no_comparison_period_mismatch": (
        "Comparison skipped: previous period ({previous_days}d) "
        "differs from current ({current_days}d)"
    ),
    "no_comparison_missing_streams": (
        "Comparison incomplete: some data streams unavailable in previous report"
    ),
    # Positive change narratives (period-over-period)
    "traffic_up_positive": "Traffic up {pct}% - business growing",
    "latency_down": "Response time improved by {ms}ms - faster user experience",
    "apex_proxied": "Apex record now proxied - origin IP protected",
    "ssl_upgraded": "Encryption upgraded to Full/Strict - security improved",
    "dnssec_enabled": "DNSSEC now active - spoofing protection enabled",
    # Posture warnings
    "apex_unproxied": "Apex record not proxied - origin IP exposed to attackers",
    "cert_14": "Certificate expires in {days} days - renew immediately",
    "cert_30": "Certificate expires in {days} days - schedule renewal",
    "ssl_off": "TLS/SSL mode Off - enable HTTPS immediately.",
    "ssl_flexible": ("TLS/SSL mode Flexible (HTTP may reach origin) - move to Full (Strict) now."),
    "ssl_full": (
        "TLS/SSL mode Full without CA-validated origin certificate - upgrade to Full (Strict)."
    ),
    "dnssec_off": "DNSSEC disabled - domain spoofing risk",
    "waf_off": "Web Application Firewall disabled - no attack protection",
    "ddos_off": "DDoS protection disabled - availability at risk",
    "no_cert_packs": "No SSL certificate deployed - traffic not encrypted",
    "security_level_off_or_minimal": (
        "Cloudflare Security Level is off or essentially off - known threats are barely challenged."
    ),
    # Correlations (multi-signal)
    "origin_overloaded": (
        "Origin overloaded: high error rate ({err_pct}%) with slow response ({latency_ms}ms)"
    ),
    "cache_inefficient": (
        "Caching inefficient: {cache_hit}% hit rate with {bandwidth_gb}GB bandwidth - cost impact"
    ),
    "apex_ddos_mismatch": ("Origin exposed: apex not proxied, but DDoS protection requires proxy"),
    "ssl_flexible_with_cert": (
        "Encryption weak: Flexible mode allows HTTP - upgrade to Full/Strict"
    ),
    "threats_high": (
        "Active attack: {mitigation_pct}% of requests mitigated - WAF blocking threats"
    ),
    "audit_high": "Unusual activity: {events} audit events in period - review if expected",
    "security_under_attack_mode": (
        "Cloudflare Under Attack mode is on - confirm this is intentional and temporary."
    ),
    "security_level_low": (
        "Security Level is Low - consider default or automatic for stronger baseline protection."
    ),
    "security_level_high": (
        "Security Level is High - watch for false positives blocking legitimate users."
    ),
    # Period comparisons (metrics vs prior period)
    "threats_up_traffic_flat": ("Possible targeted attack: threats up {pct}% with stable traffic"),
    "threats_up_traffic_up": "Attack volume increasing: threats up {pct}% alongside traffic",
    "traffic_up_comparison": "Traffic growth: {pct}% increase from previous period",
    "traffic_down_comparison": "Traffic decline: {pct}% decrease from previous period",
    "latency_up_comparison": "Performance degraded: response time increased by {ms}ms",
    "cache_hit_down": "Cache efficiency dropped: {pp}% decrease - review caching rules",
    "apex_regression": "Security regression: apex changed from {previous} to {current}",
    "ssl_regression": "Security regression: SSL mode changed from {previous} to {current}",
    # Recommended actions
    "enable_always_https": ("Enable Always Use HTTPS - redirects HTTP to HTTPS for all traffic."),
    "review_dnssec": "Enable DNSSEC - prevents DNS spoofing and domain hijacking.",
    "review_ssl_mode": (
        "Change SSL/TLS mode to Full (Strict) for end-to-end encryption "
        "with certificate validation."
    ),
    "ssl_upgrade_full_to_strict": (
        "Upgrade TLS/SSL mode from Full to Full (Strict) - enables CA certificate validation."
    ),
    "review_waf_posture": ("Review Web Application Firewall (WAF) and rate-limiting baseline."),
    "enable_apex_proxy": "Enable proxy on apex A/AAAA record - hides origin IP.",
    "plan_tls_renewal": "Renew TLS certificate before expiry - prevents outages.",
    "review_audit_activity": "Review audit log - check for unauthorized changes.",
    "enable_cloudflare_security_level_auto": (
        "Enable Cloudflare automatic Security Level (Security app) - avoid off or essentially off."
    ),
}

PREFIXES: dict[str, str] = {
    "positive": "[OK]",
    "info": "[i]",
    "warning": "[!]",
    "critical": "[!!]",
}


def format_line_with_severity_prefix(severity: str, body: str) -> str:
    """Return one executive takeaway line: severity tag plus rendered phrase body."""
    return f"{PREFIXES[severity]} {body}"


def render_phrase(key: str, **kwargs: object) -> str:
    """Format the template for ``key`` using ``kwargs``."""
    template = PHRASES[key]
    return template.format(**kwargs)
