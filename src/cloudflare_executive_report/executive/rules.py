"""Comparison, regression, and correlation rules for executive takeaways."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from cloudflare_executive_report.executive.phrase_catalog import PREFIXES, render_phrase


def _as_dict(v: Any) -> dict[str, Any]:
    return v if isinstance(v, dict) else {}


def _as_int(v: Any) -> int:
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


def _as_float(v: Any) -> float:
    try:
        return float(v or 0.0)
    except (TypeError, ValueError):
        return 0.0


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


def _period_bounds(period: dict[str, Any]) -> tuple[object, object] | None:
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


@dataclass
class RuleMessage:
    phrase_key: str
    severity: str
    message: str

    def display(self) -> str:
        return f"{PREFIXES[self.severity]} {self.message}"


@dataclass
class ComparisonGate:
    allowed: bool
    warning: RuleMessage | None


def evaluate_comparison_gate(
    *,
    current_zone_id: str,
    previous_report: dict[str, Any] | None,
    current_period: dict[str, Any],
) -> ComparisonGate:
    if not previous_report:
        return ComparisonGate(
            allowed=False,
            warning=RuleMessage(
                phrase_key="no_comparison.first_report",
                severity="warning",
                message=render_phrase("no_comparison.first_report"),
            ),
        )
    previous_period = _as_dict(previous_report.get("report_period"))
    current_days = _period_days(current_period)
    previous_days = _period_days(previous_period)
    previous_bounds = _period_bounds(previous_period)
    current_bounds = _period_bounds(current_period)
    if previous_bounds is None or current_bounds is None or previous_bounds[1] >= current_bounds[0]:
        return ComparisonGate(
            allowed=False,
            warning=RuleMessage(
                phrase_key="no_comparison.period_mismatch",
                severity="warning",
                message=render_phrase(
                    "no_comparison.period_mismatch",
                    previous_days=previous_days,
                    current_days=current_days,
                ),
            ),
        )
    if current_days <= 0 or previous_days <= 0 or current_days != previous_days:
        return ComparisonGate(
            allowed=False,
            warning=RuleMessage(
                phrase_key="no_comparison.period_mismatch",
                severity="warning",
                message=render_phrase(
                    "no_comparison.period_mismatch",
                    previous_days=previous_days,
                    current_days=current_days,
                ),
            ),
        )
    prev_zone = _find_zone(previous_report, current_zone_id)
    if not prev_zone:
        return ComparisonGate(
            allowed=False,
            warning=RuleMessage(
                phrase_key="no_comparison.first_report",
                severity="warning",
                message=render_phrase("no_comparison.first_report"),
            ),
        )
    needed = ("http", "security", "dns")
    if any(_as_dict(prev_zone).get(k) in (None, {}) for k in needed):
        return ComparisonGate(
            allowed=False,
            warning=RuleMessage(
                phrase_key="no_comparison.missing_streams",
                severity="warning",
                message=render_phrase("no_comparison.missing_streams"),
            ),
        )
    return ComparisonGate(allowed=True, warning=None)


def _find_zone(report: dict[str, Any], zone_id: str) -> dict[str, Any] | None:
    for zone in report.get("zones") or []:
        if isinstance(zone, dict) and str(zone.get("zone_id") or "") == zone_id:
            return zone
    return None


def build_rule_messages(
    *,
    current_zone: dict[str, Any],
    previous_zone: dict[str, Any] | None,
    comparison_allowed: bool,
) -> dict[str, list[RuleMessage]]:
    positive: list[RuleMessage] = []
    warnings: list[RuleMessage] = []
    correlations: list[RuleMessage] = []
    comparisons: list[RuleMessage] = []
    actions: list[RuleMessage] = []

    zh = _as_dict(current_zone.get("zone_health"))
    http = _as_dict(current_zone.get("http"))
    sec = _as_dict(current_zone.get("security"))
    cache = _as_dict(current_zone.get("cache"))
    ha = _as_dict(current_zone.get("http_adaptive"))
    dr = _as_dict(current_zone.get("dns_records"))
    au = _as_dict(current_zone.get("audit"))
    ce = _as_dict(current_zone.get("certificates"))

    apex_unproxied = _as_int(dr.get("apex_unproxied_a_aaaa")) > 0
    ssl_mode = str(zh.get("ssl_mode") or "").strip().lower()
    security_level = str(zh.get("security_level") or "").strip().lower()
    dnssec = str(zh.get("dnssec_status") or "").strip().lower()
    ddos = str(zh.get("ddos_protection") or "").strip().lower()
    waf_on = _as_int(zh.get("security_rules_active")) > 0
    exp_days = _as_int(ce.get("expiring_in_30_days"))
    cert_packs = _as_int(ce.get("total_certificate_packs"))

    if apex_unproxied:
        warnings.append(_msg("warning.apex_unproxied", "warning"))
    if ssl_mode == "off":
        warnings.append(_msg("warning.ssl_off", "critical"))
    elif ssl_mode == "flexible":
        warnings.append(_msg("warning.ssl_flexible", "critical"))
    elif ssl_mode == "full":
        warnings.append(_msg("warning.ssl_full", "warning"))
    if dnssec in {"off", "disabled"}:
        warnings.append(_msg("warning.dnssec_off", "warning"))
    if security_level in {"off", "essentially_off"}:
        warnings.append(_msg("warning.security_level_off_or_minimal", "critical"))
        actions.append(_msg("action.enable_cloudflare_security_level_auto", "info"))
    elif security_level == "under_attack":
        correlations.append(_msg("correlation.security_under_attack_mode", "info"))
    elif security_level == "low":
        correlations.append(_msg("correlation.security_level_low", "info"))
    elif security_level == "high":
        correlations.append(_msg("correlation.security_level_high", "info"))
    if not waf_on:
        warnings.append(_msg("warning.waf_off", "warning"))
    if ddos in {"off", "disabled"}:
        warnings.append(_msg("warning.ddos_off", "warning"))
    if cert_packs == 0:
        warnings.append(_msg("warning.no_cert_packs", "warning"))
    if 0 < exp_days <= 14:
        warnings.append(_msg("warning.cert_14", "critical", days=exp_days))
    elif 14 < exp_days <= 30:
        warnings.append(_msg("warning.cert_30", "warning", days=exp_days))

    err_5xx = _as_float(ha.get("status_5xx_rate_pct"))
    latency = _as_float(ha.get("origin_response_duration_avg_ms"))
    cache_hit = _as_float(cache.get("cache_hit_ratio") or http.get("cache_hit_ratio"))
    bandwidth_gb = _as_int(http.get("total_bandwidth_bytes")) / (1024.0**3)
    mitigation = _as_float(sec.get("mitigation_rate_pct"))
    audits = _as_int(au.get("total_events"))
    if err_5xx > 0.5 and latency > 500:
        correlations.append(
            _msg(
                "correlation.origin_overloaded",
                "critical",
                err_pct=round(err_5xx, 2),
                latency_ms=int(round(latency)),
            )
        )
    if cache_hit < 10 and bandwidth_gb > 10:
        correlations.append(
            _msg(
                "correlation.cache_inefficient",
                "warning",
                cache_hit=round(cache_hit, 1),
                bandwidth_gb=int(round(bandwidth_gb)),
            )
        )
    if apex_unproxied and ddos == "on":
        correlations.append(_msg("correlation.apex_ddos_mismatch", "warning"))
    if ssl_mode == "flexible" and cert_packs > 0:
        correlations.append(_msg("correlation.ssl_flexible_with_cert", "warning"))
    if mitigation > 5.0:
        correlations.append(
            _msg("correlation.threats_high", "warning", mitigation_pct=round(mitigation, 1))
        )
    if audits > 50:
        correlations.append(_msg("correlation.audit_high", "warning", events=audits))

    # Action rules migrated from summary.py to keep rule ownership centralized.
    always_https = str(zh.get("always_https") or "").strip().lower()
    total_requests = _as_int(http.get("total_requests"))
    encrypted_requests = _as_int(http.get("encrypted_requests"))
    enc_gap = max(0, total_requests - encrypted_requests)
    enc_gap_pct = (100.0 * enc_gap / total_requests) if total_requests > 0 else 0.0
    if always_https != "on" or (total_requests > 0 and enc_gap_pct > 5.0):
        actions.append(_msg("action.enable_always_https", "info"))
    if dnssec in {"disabled", "off", "unavailable"}:
        actions.append(_msg("action.review_dnssec", "info"))
    if ssl_mode == "full":
        actions.append(_msg("action.ssl_upgrade_full_to_strict", "info"))
    elif ssl_mode not in {"strict", "full_strict"}:
        actions.append(_msg("action.review_ssl_mode", "info"))
    if not waf_on:
        actions.append(_msg("action.review_waf_posture", "info"))
    if apex_unproxied:
        actions.append(_msg("action.enable_apex_proxy", "info"))
    if len(ce) and ce.get("unavailable") is not True and exp_days > 0:
        actions.append(_msg("action.plan_tls_renewal", "info"))
    if len(au) and au.get("unavailable") is not True and audits > 50:
        actions.append(_msg("action.review_audit_activity", "info"))

    if previous_zone and comparison_allowed:
        p_http = _as_dict(previous_zone.get("http"))
        p_sec = _as_dict(previous_zone.get("security"))
        p_ha = _as_dict(previous_zone.get("http_adaptive"))
        p_dr = _as_dict(previous_zone.get("dns_records"))
        p_zh = _as_dict(previous_zone.get("zone_health"))
        pct_traffic = _percent_delta(
            float(_as_int(http.get("total_requests"))),
            float(_as_int(p_http.get("total_requests"))),
        )
        pct_threats = _percent_delta(
            float(_as_int(sec.get("mitigated_count"))),
            float(_as_int(p_sec.get("mitigated_count"))),
        )
        if abs(pct_traffic) > 20:
            if pct_traffic > 0:
                comparisons.append(
                    _msg("comparison.traffic_up", "info", pct=int(round(pct_traffic)))
                )
                positive.append(
                    _msg("positive.traffic_up", "positive", pct=int(round(pct_traffic)))
                )
            else:
                comparisons.append(
                    _msg("comparison.traffic_down", "warning", pct=abs(int(round(pct_traffic))))
                )
        if pct_threats > 100:
            if abs(pct_traffic) < 10:
                comparisons.append(
                    _msg(
                        "comparison.threats_up_traffic_flat",
                        "critical",
                        pct=int(round(pct_threats)),
                    )
                )
            else:
                comparisons.append(
                    _msg("comparison.threats_up_traffic_up", "warning", pct=int(round(pct_threats)))
                )
        latency_delta = _as_float(ha.get("origin_response_duration_avg_ms")) - _as_float(
            p_ha.get("origin_response_duration_avg_ms")
        )
        if latency_delta > 100:
            comparisons.append(
                _msg("comparison.latency_up", "warning", ms=int(round(latency_delta)))
            )
        elif latency_delta < -10:
            positive.append(
                _msg("positive.latency_down", "positive", ms=abs(int(round(latency_delta))))
            )
        cache_delta = _pp_delta(
            _as_float(cache.get("cache_hit_ratio") or http.get("cache_hit_ratio")),
            _as_float(p_http.get("cache_hit_ratio")),
        )
        if cache_delta < -15:
            comparisons.append(
                _msg("comparison.cache_hit_down", "warning", pp=abs(int(round(cache_delta))))
            )
        p_apex = _as_int(p_dr.get("apex_unproxied_a_aaaa"))
        c_apex = _as_int(dr.get("apex_unproxied_a_aaaa"))
        if p_apex == 0 and c_apex > 0:
            comparisons.append(
                _msg(
                    "comparison.apex_regression", "critical", previous="proxied", current="dns-only"
                )
            )
        if p_apex > 0 and c_apex == 0:
            positive.append(_msg("positive.apex_proxied", "positive"))
        p_ssl = str(p_zh.get("ssl_mode") or "").strip().lower()
        c_ssl = str(zh.get("ssl_mode") or "").strip().lower()
        if p_ssl in {"strict", "full_strict"} and c_ssl == "flexible":
            comparisons.append(
                _msg("comparison.ssl_regression", "critical", previous=p_ssl, current=c_ssl)
            )
        if p_ssl == "flexible" and c_ssl in {"strict", "full", "full_strict"}:
            positive.append(_msg("positive.ssl_upgraded", "positive"))
        p_dnssec = str(p_zh.get("dnssec_status") or "").strip().lower()
        if p_dnssec in {"off", "disabled"} and dnssec not in {"off", "disabled"}:
            positive.append(_msg("positive.dnssec_enabled", "positive"))

    return {
        "positive_changes": positive,
        "warnings": warnings,
        "correlations": correlations,
        "comparisons": comparisons,
        "actions": actions,
    }


def _msg(key: str, severity: str, **kwargs: object) -> RuleMessage:
    return RuleMessage(phrase_key=key, severity=severity, message=render_phrase(key, **kwargs))
