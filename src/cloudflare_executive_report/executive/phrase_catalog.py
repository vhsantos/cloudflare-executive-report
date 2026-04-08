"""Approved phrase catalog for CTO takeaways.

All wording in this file is sourced from the cto-resume-v2 guide.
Do not invent phrasing outside these templates.
"""

from __future__ import annotations

PHRASES: dict[str, str] = {
    # No comparison scenarios
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
    "warning.ssl_flexible": "Encryption not enforced - upgrade to Full/Strict",
    "warning.dnssec_off": "DNSSEC disabled - domain spoofing risk",
    "warning.security_low": "Security level set to low - increase to Medium/High",
    "warning.security_medium": "Security level at Medium - consider High for sensitive data",
    "warning.waf_off": "Web Application Firewall disabled - no attack protection",
    "warning.ddos_off": "DDoS protection disabled - availability at risk",
    "warning.no_cert_packs": "No SSL certificate deployed - traffic not encrypted",
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
    "action.review_ssl_mode": "Change SSL mode to Full (Strict) for end-to-end encryption.",
    "action.review_waf_posture": (
        "Review Web Application Firewall (WAF) and rate-limiting baseline."
    ),
    "action.enable_apex_proxy": "Enable proxy on apex A/AAAA record - hides origin IP.",
    "action.plan_tls_renewal": "Renew TLS certificate before expiry - prevents outages.",
    "action.review_audit_activity": "Review audit log - check for unauthorized changes.",
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
