"""Approved phrase catalog for CTO takeaways.

All wording in this file is sourced from the cto-resume-v2 guide.
Do not invent phrasing outside these templates.
"""

from __future__ import annotations

PHRASES: dict[str, str] = {
    "comparison.baseline_reference": "Comparing to: {start} to {end}",
    "no_comparison.first_report": "First report for this zone - no prior data for comparison",
    "no_comparison.period_mismatch": (
        "Comparison skipped: previous period ({previous_days}d) "
        "differs from current ({current_days}d)"
    ),
    "no_comparison.missing_streams": (
        "Comparison incomplete: some data streams unavailable in previous report"
    ),
    # Positive
    "positive.traffic_up": "Traffic up {pct}% - business growing",
    "positive.latency_down": "Response time improved by {ms}ms - faster user experience",
    "positive.apex_proxied": "Apex record now proxied - origin IP protected",
    "positive.ssl_upgraded": "Encryption upgraded to Full/Strict - security improved",
    "positive.dnssec_enabled": "DNSSEC now active - spoofing protection enabled",
    # Warnings
    "warning.apex_unproxied": "Apex record not proxied - origin IP exposed to attackers",
    "warning.cert_14": "Certificate expires in {days} days - renew immediately",
    "warning.cert_30": "Certificate expires in {days} days - schedule renewal",
    "warning.ssl_off": "TLS/SSL mode Off - enable HTTPS immediately.",
    "warning.ssl_flexible": (
        "TLS/SSL mode Flexible (HTTP may reach origin) - move to Full (Strict) now."
    ),
    "warning.ssl_full": (
        "TLS/SSL mode Full without CA-validated origin certificate - upgrade to Full (Strict)."
    ),
    "warning.dnssec_off": "DNSSEC disabled - domain spoofing risk",
    "warning.waf_off": "Web Application Firewall disabled - no attack protection",
    "warning.ddos_off": "DDoS protection disabled - availability at risk",
    "warning.no_cert_packs": "No SSL certificate deployed - traffic not encrypted",
    "warning.security_level_off_or_minimal": (
        "Cloudflare Security Level is off or essentially off - known threats are barely challenged."
    ),
    # Correlations
    "correlation.origin_overloaded": (
        "Origin overloaded: high error rate ({err_pct}%) with slow response ({latency_ms}ms)"
    ),
    "correlation.cache_inefficient": (
        "Caching inefficient: {cache_hit}% hit rate with {bandwidth_gb}GB bandwidth - cost impact"
    ),
    "correlation.apex_ddos_mismatch": (
        "Origin exposed: apex not proxied, but DDoS protection requires proxy"
    ),
    "correlation.ssl_flexible_with_cert": (
        "Encryption weak: Flexible mode allows HTTP - upgrade to Full/Strict"
    ),
    "correlation.threats_high": (
        "Active attack: {mitigation_pct}% of requests mitigated - WAF blocking threats"
    ),
    "correlation.audit_high": (
        "Unusual activity: {events} audit events in period - review if expected"
    ),
    "correlation.security_under_attack_mode": (
        "Cloudflare Under Attack mode is on - confirm this is intentional and temporary."
    ),
    "correlation.security_level_low": (
        "Security Level is Low - consider default or automatic for stronger baseline protection."
    ),
    "correlation.security_level_high": (
        "Security Level is High - watch for false positives blocking legitimate users."
    ),
    # Comparisons
    "comparison.threats_up_traffic_flat": (
        "Possible targeted attack: threats up {pct}% with stable traffic"
    ),
    "comparison.threats_up_traffic_up": (
        "Attack volume increasing: threats up {pct}% alongside traffic"
    ),
    "comparison.traffic_up": "Traffic growth: {pct}% increase from previous period",
    "comparison.traffic_down": "Traffic decline: {pct}% decrease from previous period",
    "comparison.latency_up": "Performance degraded: response time increased by {ms}ms",
    "comparison.cache_hit_down": "Cache efficiency dropped: {pp}% decrease - review caching rules",
    "comparison.apex_regression": (
        "Security regression: apex changed from {previous} to {current}"
    ),
    "comparison.ssl_regression": (
        "Security regression: SSL mode changed from {previous} to {current}"
    ),
    # Actions
    "action.enable_always_https": (
        "Enable Always Use HTTPS - redirects HTTP to HTTPS for all traffic."
    ),
    "action.review_dnssec": "Enable DNSSEC - prevents DNS spoofing and domain hijacking.",
    "action.review_ssl_mode": (
        "Change SSL/TLS mode to Full (Strict) for end-to-end encryption "
        "with certificate validation."
    ),
    "action.ssl_upgrade_full_to_strict": (
        "Upgrade TLS/SSL mode from Full to Full (Strict) - enables CA certificate validation."
    ),
    "action.review_waf_posture": (
        "Review Web Application Firewall (WAF) and rate-limiting baseline."
    ),
    "action.enable_apex_proxy": "Enable proxy on apex A/AAAA record - hides origin IP.",
    "action.plan_tls_renewal": "Renew TLS certificate before expiry - prevents outages.",
    "action.review_audit_activity": "Review audit log - check for unauthorized changes.",
    "action.enable_cloudflare_security_level_auto": (
        "Enable Cloudflare automatic Security Level (Security app) - avoid off or essentially off."
    ),
}

PREFIXES: dict[str, str] = {
    "positive": "[OK]",
    "info": "[i]",
    "warning": "[!]",
    "critical": "[!!]",
}


def render_phrase(key: str, **kwargs: object) -> str:
    template = PHRASES[key]
    return template.format(**kwargs)
