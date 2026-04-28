"""Comparison and posture rules for the executive summary (takeaways + actions)."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

from cloudflare_executive_report.common.constants import (
    AUDIT_EVENTS_THRESHOLD,
    BANDWIDTH_GB_MIN_THRESHOLD,
    CACHE_DELTA_WARNING_PP,
    CACHE_HIT_RATIO_LOW_THRESHOLD,
    CERT_EXPIRY_CRITICAL_DAYS,
    CERT_EXPIRY_WARNING_DAYS,
    HSTS_RECOMMENDED_MAX_AGE_SECONDS,
    HTTPS_ENCRYPTED_GAP_ACTION_MAX_PCT,
    LATENCY_DELTA_WARNING_MS,
    LATENCY_DELTA_WIN_MS,
    LATENCY_WARNING_MS,
    MITIGATION_RATE_PCT_THRESHOLD,
    RELIABILITY_5XX_HEALTHY_MAX,
    RELIABILITY_5XX_WARNING_MAX,
    SKIPPED,
    THREATS_DELTA_PCT_THRESHOLD,
    TRAFFIC_DELTA_PCT_THRESHOLD,
    TRAFFIC_FLAT_DELTA_PCT,
    UNAVAILABLE,
)
from cloudflare_executive_report.common.safe_types import as_dict, as_float, as_int
from cloudflare_executive_report.executive.phrase_catalog import get_phrase

_VALID_SEVERITIES = frozenset({"positive", "warning", "critical", "info"})
_TOKEN_KEY = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")

# Report section IDs: string keys in takeaways_categorized JSON and ExecutiveLine.section.
# These are NOT severities. Severity (positive, warning, critical, info) is separate; it drives
# the [OK]/[!] prefix and tone. Section only decides which bucket a line appears in and merge
# order in the flat takeaways list (see TX_ORDER).
#
# SECT_WINS ("wins"): Improvements versus the previous report period (traffic up, latency down,
# apex proxied, SSL upgraded, DNSSEC enabled). Only emitted when comparison is allowed.
#
# SECT_RISKS ("risks"): Current-zone configuration and exposure issues (SSL mode, WAF off, apex
# unproxied, cert expiry). Comparison gate messages live in SECT_DELTAS so they do not affect
# security posture score (risks-only).
#
# SECT_SIGNALS ("signals"): Multiple observations combined in one narrative (origin errors+latency,
# cache + bandwidth, security level notes, threat rate spikes). Not the same as period deltas.
#
# SECT_DELTAS ("deltas"): Period-over-period metric deltas (traffic/threats/latency/cache vs last
# window). Includes the optional baseline line ("Comparing to: ...") when comparison is allowed.
#
# SECT_ACTIONS ("actions"): Recommended next steps only. Shown under "actions" in JSON, not mixed
# into the numbered takeaway paragraphs for PDF (flat takeaways list excludes this section).
SECT_WINS: TakeawaySection = "wins"
SECT_RISKS: TakeawaySection = "risks"
SECT_SIGNALS: TakeawaySection = "signals"
SECT_DELTAS: TakeawaySection = "deltas"
SECT_ACTIONS = "actions"


# Flatten order for PDF and the flat takeaways list.
TX_ORDER: tuple[str, ...] = (SECT_WINS, SECT_RISKS, SECT_SIGNALS, SECT_DELTAS)

TakeawaySection = Literal["wins", "risks", "signals", "deltas"]


def _period_days(period: dict[str, Any]) -> int:
    start = str(period.get("start") or "")
    end = str(period.get("end") or "")
    if not start or not end:
        return 0
    from cloudflare_executive_report.common.dates import parse_ymd

    try:
        return (parse_ymd(end) - parse_ymd(start)).days + 1
    except Exception:
        return 0


def _period_bounds(period: dict[str, Any]) -> tuple[date, date] | None:
    start = str(period.get("start") or "")
    end = str(period.get("end") or "")
    if not start or not end:
        return None
    from cloudflare_executive_report.common.dates import parse_ymd

    try:
        return parse_ymd(start), parse_ymd(end)
    except Exception:
        return None


def _percent_delta(current: float, previous: float) -> float:
    if previous == 0:
        return 0.0
    return ((current - previous) / previous) * 100.0


def _pp_delta(current: float, previous: float) -> float:
    return current - previous


def _zone_health_str(zh: dict[str, Any], key: str) -> str:
    """Lowercase string for a zone_health field, or empty if missing."""
    return str(zh.get(key) or "").strip().lower()


def _zone_health_config_known(raw: str) -> bool:
    """True when the value is present and not a fetch skip or error sentinel."""
    return bool(raw) and raw not in (UNAVAILABLE, SKIPPED)


@dataclass(frozen=True)
class ExecutiveMessageFilter:
    """Exact keys and regex patterns that suppress executive lines."""

    exact_keys: frozenset[str]
    patterns: tuple[re.Pattern[str], ...]

    @classmethod
    def empty(cls) -> ExecutiveMessageFilter:
        return cls(frozenset(), ())

    @classmethod
    def from_entries(cls, entries: Sequence[str] | None) -> ExecutiveMessageFilter:
        """Token-shaped entries match the key exactly; anything else is a regex (re.search)."""
        if not entries:
            return cls.empty()
        exact: set[str] = set()
        patterns: list[re.Pattern[str]] = []
        for raw in entries:
            s = str(raw).strip()
            if not s:
                continue
            if _TOKEN_KEY.fullmatch(s):
                exact.add(s)
            else:
                patterns.append(re.compile(s))
        return cls(frozenset(exact), tuple(patterns))

    def is_ignored(self, phrase_key: str) -> bool:
        if phrase_key in self.exact_keys:
            return True
        return any(p.search(phrase_key) for p in self.patterns)


@dataclass(frozen=True, slots=True)
class ExecutiveLine:
    """One executive line: ids, NIST tags, severity, rendered body, and report section."""

    phrase_key: str
    state: str
    check_id: str
    service: str
    nist: tuple[str, ...]
    severity: str
    body: str
    section: str


@dataclass(frozen=True, slots=True)
class ExecutiveRuleOutput:
    """Rule output: ordered takeaway lines, then actions (JSON uses action bodies only)."""

    takeaways: tuple[ExecutiveLine, ...]
    actions: tuple[ExecutiveLine, ...]

    def lines_for_section(self, section: str) -> list[ExecutiveLine]:
        """Lines in one takeaway section (for tests and JSON grouping)."""
        return [ln for ln in self.takeaways if ln.section == section]


@dataclass
class ComparisonGate:
    allowed: bool
    blocked_takeaway: ExecutiveLine | None


def exec_msg(
    severity: str,
    phrase_key: str,
    *,
    state: str,
    section: str,
    filt: ExecutiveMessageFilter | None = None,
    **kwargs: object,
) -> ExecutiveLine | None:
    """Render a phrase if not ignored. Severity sets the [OK]/[!] prefix; section is the group."""
    if severity not in _VALID_SEVERITIES:
        allowed = ", ".join(sorted(_VALID_SEVERITIES))
        raise ValueError(f"Invalid severity {severity!r}; expected one of: {allowed}")
    if filt is not None and filt.is_ignored(phrase_key):
        return None
    phrase_data = get_phrase(phrase_key, state)
    text = phrase_data["text"]
    if not isinstance(text, str):
        raise ValueError(f"Phrase text for {phrase_key!r} state {state!r} must be a string")
    nist_raw = phrase_data["nist"]
    if not isinstance(nist_raw, list):
        raise TypeError(f"Phrase nist for {phrase_key!r} state {state!r} must be a list")
    return ExecutiveLine(
        phrase_key=phrase_key,
        state=state,
        check_id=str(phrase_data["id"]),
        service=str(phrase_data["service"]),
        nist=tuple(str(x) for x in nist_raw),
        severity=severity,
        body=text.format(**kwargs),
        section=section,
    )


def _comparison_gate_blocked(
    phrase_key: str,
    filt: ExecutiveMessageFilter | None,
    **phrase_kwargs: object,
) -> ComparisonGate:
    """Return disallowed comparison with one deltas-section takeaway (warning)."""
    line = exec_msg(
        "warning", phrase_key, state="comparison", section=SECT_DELTAS, filt=filt, **phrase_kwargs
    )
    return ComparisonGate(allowed=False, blocked_takeaway=line)


def evaluate_comparison_gate(
    *,
    current_zone_id: str,
    previous_report: dict[str, Any] | None,
    current_period: dict[str, Any],
    message_filter: ExecutiveMessageFilter | None = None,
) -> ComparisonGate:
    """Whether prior-period comparison is allowed; otherwise one posture takeaway explaining why."""
    filt = message_filter
    if not previous_report:
        return _comparison_gate_blocked("comparison_first_report", filt)

    previous_period = as_dict(previous_report.get("report_period"))
    current_days = _period_days(current_period)
    previous_days = _period_days(previous_period)
    previous_bounds = _period_bounds(previous_period)
    current_bounds = _period_bounds(current_period)
    bounds_bad = (
        previous_bounds is None or current_bounds is None or previous_bounds[1] >= current_bounds[0]
    )

    days_bad = current_days <= 0 or previous_days <= 0 or current_days != previous_days
    if bounds_bad or days_bad:
        return _comparison_gate_blocked(
            "comparison_period_mismatch",
            filt,
            previous_days=previous_days,
            current_days=current_days,
        )

    prev_zone = _find_zone(previous_report, current_zone_id)
    if not prev_zone:
        return _comparison_gate_blocked("comparison_first_report", filt)

    # TODO: that should return a quick check if comparison is possible or not.
    # We should put this as constante and evaluate this check to be much more efficient
    # Core streams required for comparison
    needed = ("http", "dns")
    if any(as_dict(prev_zone).get(k) in (None, {}) for k in needed):
        return _comparison_gate_blocked("comparison_missing_streams", filt)

    return ComparisonGate(allowed=True, blocked_takeaway=None)


def _find_zone(report: dict[str, Any], zone_id: str) -> dict[str, Any] | None:
    for zone in report.get("zones") or []:
        if isinstance(zone, dict) and str(zone.get("zone_id") or "") == zone_id:
            return zone
    return None


def build_executive_rule_output(
    *,
    current_zone: dict[str, Any],
    previous_zone: dict[str, Any] | None,
    comparison_allowed: bool,
    message_filter: ExecutiveMessageFilter | None = None,
    gate_warning: ExecutiveLine | None = None,
    comparison_baseline: ExecutiveLine | None = None,
) -> ExecutiveRuleOutput:
    """Run posture and comparison rules; return ordered takeaways and actions."""
    filt = message_filter or ExecutiveMessageFilter.empty()
    sections: dict[str, list[ExecutiveLine]] = {k: [] for k in TX_ORDER}
    actions: list[ExecutiveLine] = []

    def add_takeaway(
        section: TakeawaySection,
        severity: str,
        phrase_key: str,
        *,
        state: str,
        **kwargs: object,
    ) -> None:
        line = exec_msg(severity, phrase_key, state=state, section=section, filt=filt, **kwargs)
        if line:
            sections[section].append(line)

    def add_action(severity: str, phrase_key: str, *, state: str, **kwargs: object) -> None:
        line = exec_msg(
            severity, phrase_key, state=state, section=SECT_ACTIONS, filt=filt, **kwargs
        )
        if line:
            actions.append(line)

    zh = as_dict(current_zone.get("zone_health"))
    http = as_dict(current_zone.get("http"))
    sec = as_dict(current_zone.get("security"))
    cache = as_dict(current_zone.get("cache"))
    ha = as_dict(current_zone.get("http_adaptive"))
    dr = as_dict(current_zone.get("dns_records"))
    au = as_dict(current_zone.get("audit"))
    ce = as_dict(current_zone.get("certificates"))
    email = as_dict(current_zone.get("email"))

    apex_unproxied = as_int(dr.get("apex_unproxied_a_aaaa")) > 0
    ssl_mode = str(zh.get("ssl_mode") or "").strip().lower()
    security_level = str(zh.get("security_level") or "").strip().lower()
    dnssec = str(zh.get("dnssec_status") or "").strip().lower()
    ddos = str(zh.get("ddos_protection") or "").strip().lower()
    waf_on = as_int(zh.get("security_rules_active")) > 0
    exp_days = as_int(ce.get("expiring_in_30_days"))
    cert_packs = as_int(ce.get("total_certificate_packs"))

    if apex_unproxied:
        add_takeaway(SECT_RISKS, "warning", "apex_proxy", state="risk")
    if ssl_mode == "off":
        add_takeaway(SECT_RISKS, "critical", "ssl_mode_off", state="risk")
    elif ssl_mode == "flexible":
        add_takeaway(SECT_RISKS, "critical", "ssl_mode_flexible", state="risk")
    elif ssl_mode == "full":
        add_takeaway(SECT_RISKS, "warning", "ssl_mode_full", state="risk")

    min_tls = _zone_health_str(zh, "min_tls_version")
    if _zone_health_config_known(min_tls):
        if min_tls in ("1.0", "1.1"):
            add_takeaway(SECT_RISKS, "critical", "min_tls_version", state="risk", version=min_tls)
        elif min_tls == "1.2":
            add_takeaway(SECT_SIGNALS, "info", "min_tls_version", state="observation")

    tls13 = _zone_health_str(zh, "tls_1_3")
    if _zone_health_config_known(tls13) and tls13 not in ("on", "zrt"):
        add_takeaway(SECT_RISKS, "warning", "tls_1_3", state="risk")

    hsts = zh.get("hsts")
    hsts_d = hsts if isinstance(hsts, dict) else {}
    if not hsts_d.get("skipped") and hsts_d.get("available") is True:
        always_https_on = _zone_health_str(zh, "always_https") == "on"
        edge_uses_tls = ssl_mode not in ("", "off")
        hsts_enabled = hsts_d.get("enabled")
        if hsts_enabled is False and always_https_on and edge_uses_tls:
            add_takeaway(SECT_RISKS, "warning", "hsts", state="risk")
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
                    SECT_SIGNALS,
                    "info",
                    "hsts",
                    state="observation",
                    issues="; ".join(hsts_issues),
                )

    browser_chk = _zone_health_str(zh, "browser_check")
    if _zone_health_config_known(browser_chk) and browser_chk != "on":
        add_takeaway(SECT_RISKS, "warning", "browser_integrity", state="risk")

    email_obs = _zone_health_str(zh, "email_obfuscation")
    if _zone_health_config_known(email_obs) and email_obs != "on":
        add_takeaway(SECT_SIGNALS, "info", "email_obfuscation", state="observation")

    opp_enc = _zone_health_str(zh, "opportunistic_encryption")
    if _zone_health_config_known(opp_enc) and opp_enc != "on":
        add_takeaway(SECT_SIGNALS, "info", "opportunistic_encryption", state="observation")

    if dnssec in {"off", "disabled"}:
        add_takeaway(SECT_RISKS, "warning", "dnssec", state="risk")
    if security_level in {"off", "essentially_off"}:
        add_takeaway(SECT_RISKS, "critical", "security_level_off", state="risk")
        add_action("info", "security_level_off", state="action")
    elif security_level == "under_attack":
        add_takeaway(SECT_SIGNALS, "info", "security_level_under_attack", state="observation")
    elif security_level == "low":
        add_takeaway(SECT_SIGNALS, "info", "security_level_low", state="observation")
    elif security_level == "high":
        add_takeaway(SECT_SIGNALS, "info", "security_level_high", state="observation")
    if not waf_on:
        add_takeaway(SECT_RISKS, "warning", "waf", state="risk")
    if ddos in {"off", "disabled"}:
        add_takeaway(SECT_RISKS, "warning", "ddos_protection", state="risk")
    if cert_packs == 0:
        add_takeaway(SECT_RISKS, "warning", "cert_presence", state="risk")
    if 0 < exp_days <= CERT_EXPIRY_CRITICAL_DAYS:
        add_takeaway(SECT_RISKS, "critical", "cert_expire_14", state="risk", days=exp_days)
    elif CERT_EXPIRY_CRITICAL_DAYS < exp_days <= CERT_EXPIRY_WARNING_DAYS:
        add_takeaway(SECT_RISKS, "warning", "cert_expire_30", state="risk", days=exp_days)

    err_5xx = as_float(ha.get("status_5xx_rate_pct"))
    latency = as_float(ha.get("origin_response_duration_avg_ms"))
    cache_hit = as_float(cache.get("cache_hit_ratio") or http.get("cache_hit_ratio"))
    bandwidth_gb = as_int(http.get("total_bandwidth_bytes")) / (1024.0**3)
    mitigation = as_float(sec.get("mitigation_rate_pct"))
    audits = as_int(au.get("total_events"))
    if err_5xx > RELIABILITY_5XX_WARNING_MAX:
        e5 = round(err_5xx, 2)
        add_takeaway(
            SECT_SIGNALS,
            "critical",
            "origin_errors_high",
            state="observation",
            err_pct=e5,
        )
    elif err_5xx > RELIABILITY_5XX_HEALTHY_MAX and latency > LATENCY_WARNING_MS:
        e5, lms = round(err_5xx, 2), round(latency)
        add_takeaway(
            SECT_SIGNALS,
            "warning",
            "origin_health",
            state="observation",
            err_pct=e5,
            latency_ms=lms,
        )
    if cache_hit < CACHE_HIT_RATIO_LOW_THRESHOLD and bandwidth_gb > BANDWIDTH_GB_MIN_THRESHOLD:
        ch, gbw = round(cache_hit, 1), round(bandwidth_gb)
        add_takeaway(
            SECT_SIGNALS,
            "warning",
            "cache_efficiency",
            state="observation",
            cache_hit=ch,
            bandwidth_gb=gbw,
        )
    if apex_unproxied and ddos == "on":
        add_takeaway(SECT_SIGNALS, "warning", "apex_ddos_alignment", state="observation")
    if ssl_mode == "flexible" and cert_packs > 0:
        add_takeaway(SECT_SIGNALS, "warning", "ssl_mode_flexible", state="observation")
    if mitigation > MITIGATION_RATE_PCT_THRESHOLD:
        add_takeaway(
            SECT_SIGNALS,
            "warning",
            "threat_activity",
            state="observation",
            mitigation_pct=round(mitigation, 1),
        )
    if audits > AUDIT_EVENTS_THRESHOLD:
        add_takeaway(SECT_SIGNALS, "warning", "audit_activity", state="observation", events=audits)

    # ------------------------------------------------------------------
    # Email Security
    # ------------------------------------------------------------------
    dmarc = str(email.get("dns_dmarc_policy") or "").lower()
    spf = str(email.get("dns_spf_policy") or "").lower()
    dkim = bool(email.get("dns_dkim_configured"))

    if dmarc == "none":
        add_takeaway(SECT_RISKS, "critical", "email_dmarc_none", state="risk")
        add_action("info", "email_dmarc_none", state="action")
    elif dmarc == "quarantine":
        add_takeaway(SECT_RISKS, "warning", "email_dmarc_quarantine", state="risk")
        add_action("info", "email_dmarc_quarantine", state="action")

    if spf == "none":
        add_takeaway(SECT_RISKS, "warning", "email_spf_missing", state="risk")
        add_action("info", "email_spf_missing", state="action")
    elif spf == "softfail":
        add_takeaway(SECT_SIGNALS, "info", "email_spf_softfail", state="observation")
        add_action("info", "email_spf_softfail", state="action")

    if not dkim:
        add_takeaway(SECT_RISKS, "warning", "email_dkim_missing", state="risk")
        add_action("info", "email_dkim_missing", state="action")

    fail_pct = 100.0 - float(email.get("dmarc_pass_rate_pct") or 100.0)
    if fail_pct > 10.0:  # Use a fixed 10% threshold for now
        add_takeaway(
            SECT_SIGNALS,
            "warning",
            "email_high_fail_rate",
            state="observation",
            fail_pct=round(fail_pct, 1),
        )

    dropped = int(email.get("dropped") or 0)
    if dropped > 0:
        add_takeaway(
            SECT_SIGNALS, "info", "email_routing_drops", state="observation", dropped=dropped
        )

    always_https = str(zh.get("always_https") or "").strip().lower()
    total_requests = as_int(http.get("total_requests"))
    encrypted_requests = as_int(http.get("encrypted_requests"))
    enc_gap = max(0, total_requests - encrypted_requests)
    enc_gap_pct = (100.0 * enc_gap / total_requests) if total_requests > 0 else 0.0
    if always_https != "on":
        add_action("info", "https_enforcement", state="action")
    elif total_requests > 0 and enc_gap_pct > HTTPS_ENCRYPTED_GAP_ACTION_MAX_PCT:
        add_action(
            "info",
            "https_encryption_gap",
            state="action",
            gap_pct=round(enc_gap_pct, 1),
        )
    if dnssec in {"disabled", "off", UNAVAILABLE}:
        add_action("info", "dnssec", state="action")
    if ssl_mode == "full":
        add_action("info", "ssl_mode_full", state="action")
    elif ssl_mode not in {"strict", "full_strict"}:
        if ssl_mode == "off":
            add_action("info", "ssl_mode_off", state="action")
        else:
            add_action("info", "ssl_mode_flexible", state="action")
    if not waf_on:
        add_action("info", "waf", state="action")
    if apex_unproxied:
        add_action("info", "apex_proxy", state="action")
    if len(ce) and ce.get("unavailable") is not True and exp_days > 0:
        add_action("info", "cert_expire_30", state="action")
    if len(au) and au.get("unavailable") is not True and audits > AUDIT_EVENTS_THRESHOLD:
        add_action("info", "audit_activity", state="action")

    if previous_zone and comparison_allowed:
        p_http = as_dict(previous_zone.get("http"))
        p_sec = as_dict(previous_zone.get("security"))
        p_ha = as_dict(previous_zone.get("http_adaptive"))
        p_dr = as_dict(previous_zone.get("dns_records"))
        p_zh = as_dict(previous_zone.get("zone_health"))
        p_email = as_dict(previous_zone.get("email"))

        pct_traffic = _percent_delta(
            as_int(http.get("total_requests")),
            as_int(p_http.get("total_requests")),
        )
        pct_threats = _percent_delta(
            as_int(sec.get("mitigated_count")),
            as_int(p_sec.get("mitigated_count")),
        )
        if abs(pct_traffic) > TRAFFIC_DELTA_PCT_THRESHOLD:
            if pct_traffic > 0:
                pct_i = round(pct_traffic)
                add_takeaway(SECT_DELTAS, "info", "traffic_up", state="comparison", pct=pct_i)
                add_takeaway(SECT_WINS, "positive", "traffic_up", state="win", pct=pct_i)
            else:
                pct_dn = abs(round(pct_traffic))
                add_takeaway(SECT_DELTAS, "warning", "traffic_down", state="comparison", pct=pct_dn)
        if pct_threats > THREATS_DELTA_PCT_THRESHOLD:
            pt = round(pct_threats)
            if abs(pct_traffic) < TRAFFIC_FLAT_DELTA_PCT:
                add_takeaway(
                    SECT_DELTAS, "critical", "threats_vs_traffic_flat", state="comparison", pct=pt
                )
            else:
                add_takeaway(
                    SECT_DELTAS, "warning", "threats_vs_traffic_up", state="comparison", pct=pt
                )
        latency_delta = as_float(ha.get("origin_response_duration_avg_ms")) - as_float(
            p_ha.get("origin_response_duration_avg_ms")
        )
        if latency_delta > LATENCY_DELTA_WARNING_MS:
            ms_up = round(latency_delta)
            add_takeaway(SECT_DELTAS, "warning", "latency_delta", state="comparison", ms=ms_up)
        elif latency_delta < LATENCY_DELTA_WIN_MS:
            ms_dn = abs(round(latency_delta))
            add_takeaway(SECT_WINS, "positive", "latency_delta", state="win", ms=ms_dn)
        cache_delta = _pp_delta(
            as_float(cache.get("cache_hit_ratio") or http.get("cache_hit_ratio")),
            as_float(p_http.get("cache_hit_ratio")),
        )
        if cache_delta < CACHE_DELTA_WARNING_PP:
            pp_dn = abs(round(cache_delta))
            add_takeaway(SECT_DELTAS, "warning", "cache_efficiency", state="comparison", pp=pp_dn)
        p_apex = as_int(p_dr.get("apex_unproxied_a_aaaa"))
        c_apex = as_int(dr.get("apex_unproxied_a_aaaa"))
        if p_apex == 0 and c_apex > 0:
            add_takeaway(
                SECT_DELTAS,
                "critical",
                "apex_proxy",
                state="comparison",
                previous="proxied",
                current="dns-only",
            )
        if p_apex > 0 and c_apex == 0:
            add_takeaway(SECT_WINS, "positive", "apex_proxy", state="win")
        p_ssl = str(p_zh.get("ssl_mode") or "").strip().lower()
        c_ssl = str(zh.get("ssl_mode") or "").strip().lower()
        if p_ssl in {"strict", "full_strict"} and c_ssl == "flexible":
            add_takeaway(
                SECT_DELTAS,
                "critical",
                "ssl_mode_transition_regression",
                state="comparison",
                previous=p_ssl,
                current=c_ssl,
            )
        if p_ssl == "flexible" and c_ssl in {"strict", "full", "full_strict"}:
            add_takeaway(SECT_WINS, "positive", "ssl_mode_full", state="win")
        p_dnssec = str(p_zh.get("dnssec_status") or "").strip().lower()
        if p_dnssec in {"off", "disabled"} and dnssec not in {"off", "disabled"}:
            add_takeaway(SECT_WINS, "positive", "dnssec", state="win")

        p_dmarc = str(p_email.get("dns_dmarc_policy") or "").lower()
        if p_dmarc in ("none", "quarantine") and dmarc == "reject":
            add_takeaway(SECT_WINS, "positive", "email_dmarc_reject", state="win", previous=p_dmarc)

        p_spf = str(p_email.get("dns_spf_policy") or "").lower()
        if p_spf in ("none", "softfail") and spf == "hardfail":
            add_takeaway(SECT_WINS, "positive", "email_spf_hardfail", state="win", previous=p_spf)

        p_dkim = bool(p_email.get("dns_dkim_configured"))
        if not p_dkim and dkim:
            add_takeaway(SECT_WINS, "positive", "email_dkim_configured", state="win")

    if gate_warning is not None:
        sections[SECT_DELTAS].insert(0, gate_warning)
    if comparison_baseline is not None:
        sections[SECT_DELTAS].insert(0, comparison_baseline)

    merged_takeaways = [ln for key in TX_ORDER for ln in sections[key]]
    return ExecutiveRuleOutput(
        takeaways=tuple(merged_takeaways),
        actions=tuple(actions),
    )
