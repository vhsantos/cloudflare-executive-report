"""Zone-health posture rules: SSL, TLS, HSTS, DNSSEC, WAF, DDoS, browser, obfuscation.

Rules are conditionally applied based on whether traffic actually reaches Cloudflare edge:
- HTTP-related rules (SSL/TLS/HSTS/WAF) only apply when edge traffic exists
- DNS-related rules (DNSSEC/apex/DDoS) always apply
- Zone settings (browser/email obfuscation) always apply
"""

from __future__ import annotations

from typing import Any

from cloudflare_executive_report.common.constants import (
    HSTS_RECOMMENDED_MAX_AGE_SECONDS,
    HTTPS_ENCRYPTED_GAP_ACTION_MAX_PCT,
    SKIPPED,
    UNAVAILABLE,
)
from cloudflare_executive_report.common.safe_types import as_dict, as_int
from cloudflare_executive_report.executive.rules import (
    SECT_DELTAS,
    SECT_RISKS,
    SECT_SIGNALS,
    SECT_WINS,
)
from cloudflare_executive_report.executive.rules._context import (
    RuleContext,
    add_action,
    add_takeaway,
)


def _str(d: dict[str, Any], key: str) -> str:
    """Lowercase stripped string for a zone_health field, or empty if missing."""
    return str(d.get(key) or "").strip().lower()


def _known(raw: str) -> bool:
    """True when the value is present and not a fetch skip or error sentinel."""
    return bool(raw) and raw not in (UNAVAILABLE, SKIPPED)


def _has_edge_traffic(ctx: RuleContext) -> bool:
    """True if traffic actually reaches Cloudflare edge (HTTP or proxied DNS)."""
    # HTTP stream present -> definitely has edge traffic
    if ctx.available_streams.get("http", False):
        return True
    # DNS with proxied records -> traffic goes through Cloudflare
    dr = as_dict(ctx.current_zone.get("dns_records"))
    return as_int(dr.get("proxied_records")) > 0


def evaluate(ctx: RuleContext) -> None:
    """Evaluate zone-health rules. HTTP-related rules only apply when edge traffic exists."""
    zh = as_dict(ctx.current_zone.get("zone_health"))
    http = as_dict(ctx.current_zone.get("http"))
    dr = as_dict(ctx.current_zone.get("dns_records"))

    ssl_mode = _str(zh, "ssl_mode")
    security_level = _str(zh, "security_level")
    dnssec = _str(zh, "dnssec_status")
    ddos = _str(zh, "ddos_protection")
    waf_on = as_int(zh.get("security_rules_active")) > 0
    has_edge = _has_edge_traffic(ctx)

    # ------------------------------------------------------------------
    # DNS-related rules (always relevant)
    # ------------------------------------------------------------------

    # DNSSEC
    if dnssec in {"off", "disabled"}:
        add_takeaway(ctx, SECT_RISKS, "warning", "dnssec", state="risk")

    # DDoS protection
    if ddos in {"off", "disabled"}:
        add_takeaway(ctx, SECT_RISKS, "warning", "ddos_protection", state="risk")

    # Always-on DNS actions
    if dnssec in {"disabled", "off", UNAVAILABLE}:
        add_action(ctx, "info", "dnssec", state="action")

    # DNSSEC delta (always relevant)
    if ctx.previous_zone and ctx.comparison_allowed:
        p_zh = as_dict(ctx.previous_zone.get("zone_health"))
        p_dnssec = str(p_zh.get("dnssec_status") or "").strip().lower()
        if p_dnssec in {"off", "disabled"} and dnssec not in {"off", "disabled"}:
            add_takeaway(ctx, SECT_WINS, "positive", "dnssec", state="win")

    # ------------------------------------------------------------------
    # HTTP/Edge-related rules (only apply when edge traffic exists)
    # ------------------------------------------------------------------
    if has_edge:
        # If user only requested DNS but proxied records exist, explain why HTTP warnings appear
        if not ctx.available_streams.get("http", False):
            add_takeaway(
                ctx,
                SECT_SIGNALS,
                "info",
                "dns_only_with_proxied_records",
                state="observation",
            )

        # Apex proxy (only meaningful if traffic goes through edge)
        apex_unproxied = as_int(dr.get("apex_unproxied_a_aaaa")) > 0
        if apex_unproxied:
            add_takeaway(ctx, SECT_RISKS, "warning", "apex_proxy", state="risk")
            add_action(ctx, "info", "apex_proxy", state="action")

        # Apex + DDoS alignment signal
        if apex_unproxied and ddos == "on":
            add_takeaway(ctx, SECT_SIGNALS, "warning", "apex_ddos_alignment", state="observation")

        # SSL mode
        if ssl_mode == "off":
            add_takeaway(ctx, SECT_RISKS, "critical", "ssl_mode_off", state="risk")
        elif ssl_mode == "flexible":
            add_takeaway(ctx, SECT_RISKS, "critical", "ssl_mode_flexible", state="risk")
        elif ssl_mode == "full":
            add_takeaway(ctx, SECT_RISKS, "warning", "ssl_mode_full", state="risk")

        # Minimum TLS version
        min_tls = _str(zh, "min_tls_version")
        if _known(min_tls):
            if min_tls in ("1.0", "1.1"):
                add_takeaway(
                    ctx, SECT_RISKS, "critical", "min_tls_version", state="risk", version=min_tls
                )
            elif min_tls == "1.2":
                add_takeaway(ctx, SECT_SIGNALS, "info", "min_tls_version", state="observation")

        # TLS 1.3
        tls13 = _str(zh, "tls_1_3")
        if _known(tls13) and tls13 not in ("on", "zrt"):
            add_takeaway(ctx, SECT_RISKS, "warning", "tls_1_3", state="risk")

        # HSTS
        hsts = zh.get("hsts")
        hsts_d = hsts if isinstance(hsts, dict) else {}
        if not hsts_d.get("skipped") and hsts_d.get("available") is True:
            always_https_on = _str(zh, "always_https") == "on"
            edge_uses_tls = ssl_mode not in ("", "off")
            hsts_enabled = hsts_d.get("enabled")
            if hsts_enabled is False and always_https_on and edge_uses_tls:
                add_takeaway(ctx, SECT_RISKS, "warning", "hsts", state="risk")
            elif hsts_enabled is True:
                hsts_issues: list[str] = []
                max_age = hsts_d.get("max_age")
                if max_age is not None and max_age < HSTS_RECOMMENDED_MAX_AGE_SECONDS:
                    hsts_issues.append(
                        f"max-age is {max_age}s (set at least "
                        f"{HSTS_RECOMMENDED_MAX_AGE_SECONDS} for one year)"
                    )
                if hsts_d.get("include_subdomains") is False:
                    hsts_issues.append("Include Subdomains is off")
                if hsts_issues:
                    add_takeaway(
                        ctx,
                        SECT_SIGNALS,
                        "info",
                        "hsts",
                        state="observation",
                        issues="; ".join(hsts_issues),
                    )
        # Browser integrity check
        browser_chk = _str(zh, "browser_check")
        if _known(browser_chk) and browser_chk != "on":
            add_takeaway(ctx, SECT_RISKS, "warning", "browser_integrity", state="risk")

        # Email obfuscation
        email_obs = _str(zh, "email_obfuscation")
        if _known(email_obs) and email_obs != "on":
            add_takeaway(ctx, SECT_SIGNALS, "info", "email_obfuscation", state="observation")

        # Opportunistic encryption
        opp_enc = _str(zh, "opportunistic_encryption")
        if _known(opp_enc) and opp_enc != "on":
            add_takeaway(ctx, SECT_SIGNALS, "info", "opportunistic_encryption", state="observation")

        # Security level
        if security_level in {"off", "essentially_off"}:
            add_takeaway(ctx, SECT_RISKS, "critical", "security_level_off", state="risk")
            add_action(ctx, "info", "security_level_off", state="action")
        elif security_level == "under_attack":
            add_takeaway(
                ctx, SECT_SIGNALS, "info", "security_level_under_attack", state="observation"
            )
        elif security_level == "low":
            add_takeaway(ctx, SECT_SIGNALS, "info", "security_level_low", state="observation")
        elif security_level == "high":
            add_takeaway(ctx, SECT_SIGNALS, "info", "security_level_high", state="observation")

        # WAF (protects HTTP traffic)
        if not waf_on:
            add_takeaway(ctx, SECT_RISKS, "warning", "waf", state="risk")
            add_action(ctx, "info", "waf", state="action")

        # HTTP-related actions
        always_https = _str(zh, "always_https")
        total_requests = as_int(http.get("total_requests"))
        encrypted_requests = as_int(http.get("encrypted_requests"))
        enc_gap = max(0, total_requests - encrypted_requests)
        enc_gap_pct = (100.0 * enc_gap / total_requests) if total_requests > 0 else 0.0

        if always_https != "on":
            add_action(ctx, "info", "https_enforcement", state="action")
        elif total_requests > 0 and enc_gap_pct > HTTPS_ENCRYPTED_GAP_ACTION_MAX_PCT:
            add_action(
                ctx, "info", "https_encryption_gap", state="action", gap_pct=round(enc_gap_pct, 1)
            )

        if ssl_mode == "full":
            add_action(ctx, "info", "ssl_mode_full", state="action")
        elif ssl_mode not in {"strict", "full_strict"}:
            if ssl_mode == "off":
                add_action(ctx, "info", "ssl_mode_off", state="action")
            else:
                add_action(ctx, "info", "ssl_mode_flexible", state="action")

        # ------------------------------------------------------------------
        # Zone-health deltas: SSL and DNSSEC wins
        # ------------------------------------------------------------------
        # SSL delta
        if ctx.previous_zone and ctx.comparison_allowed:
            p_zh = as_dict(ctx.previous_zone.get("zone_health"))
            p_ssl = str(p_zh.get("ssl_mode") or "").strip().lower()
            c_ssl = str(zh.get("ssl_mode") or "").strip().lower()
            if p_ssl in {"strict", "full_strict"} and c_ssl == "flexible":
                add_takeaway(
                    ctx,
                    SECT_DELTAS,
                    "critical",
                    "ssl_mode_transition_regression",
                    state="comparison",
                    previous=p_ssl,
                    current=c_ssl,
                )
            if p_ssl == "flexible" and c_ssl in {"strict", "full", "full_strict"}:
                add_takeaway(ctx, SECT_WINS, "positive", "ssl_mode_full", state="win")
