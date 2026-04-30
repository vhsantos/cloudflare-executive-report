"""Shared executive summary derivation for JSON and PDF layers."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Any, cast

from cloudflare_executive_report.common.constants import (
    MITIGATING_SECURITY_ACTIONS,
    SECURITY_POSTURE_REFERENCE_RISK_WEIGHT,
    UNAVAILABLE,
    VERDICT_WARN_THRESHOLD,
)
from cloudflare_executive_report.common.dates import format_date_with_days_from_iso, utc_today
from cloudflare_executive_report.common.formatting import (
    format_count_compact,
    format_count_human,
    trim_decimal,
)
from cloudflare_executive_report.common.safe_types import as_dict, as_float, as_int
from cloudflare_executive_report.executive.nist_catalog import (
    NistSourceLine,
    build_nist_reference_rows,
)
from cloudflare_executive_report.executive.phrase_catalog import (
    format_line_with_severity_prefix,
    get_phrase,
)
from cloudflare_executive_report.executive.rules import (
    SECT_DELTAS,
    SECT_RISKS,
    SECT_SIGNALS,
    TX_ORDER,
    ExecutiveMessageFilter,
    ExecutiveRuleOutput,
    build_executive_rule_output,
    evaluate_comparison_gate,
    exec_msg,
)


def _grade_for_security_posture_score(score: float) -> str:
    """Letter grade for a 0-100 posture score (A+ through F)."""
    if score >= 95:
        return "A+"
    if score >= 85:
        return "A"
    if score >= 75:
        return "B"
    if score >= 65:
        return "C+"
    if score >= 55:
        return "C"
    if score >= 45:
        return "D+"
    if score >= 35:
        return "D"
    return "F"


def build_security_posture_score(rule_out: ExecutiveRuleOutput) -> dict[str, Any]:
    """Return a 0-100 security posture score from risk takeaway lines only.

    Only ``SECT_RISKS`` lines contribute. Wins, signals, deltas, and other sections are ignored
    for scoring. The score is 100 minus a linear penalty to the reference risk weight (constant).
    """
    risk_weight = 0
    for line in rule_out.takeaways:
        if line.section == SECT_RISKS:
            phrase_data = get_phrase(line.phrase_key, line.state)
            weight = phrase_data["weight"]
            if not isinstance(weight, int):
                raise ValueError(
                    f"Invalid weight for phrase key {line.phrase_key!r} state {line.state!r}"
                )
            risk_weight += weight

    if risk_weight <= 0:
        return {
            "score": 100.0,
            "grade": _grade_for_security_posture_score(100.0),
            "risk_weight": 0,
        }

    ref = SECURITY_POSTURE_REFERENCE_RISK_WEIGHT
    score = max(0.0, 100.0 - (risk_weight / ref) * 100.0)
    score = round(score, 1)
    return {
        "score": score,
        "grade": _grade_for_security_posture_score(score),
        "risk_weight": risk_weight,
    }


_DEFENSIVE_ACTIONS = MITIGATING_SECURITY_ACTIONS


def _as_str(v: Any, *, default: str = UNAVAILABLE) -> str:
    s = str(v).strip() if v is not None else ""
    return s if s else default


def _kpi_indicator(
    *,
    current: float,
    previous: float | None,
    mode: str,
    better_when_lower: bool = False,
) -> str:
    if previous is None:
        return ""

    def _prefix(improved: bool) -> str:
        return "G:" if improved else "R:"

    if mode == "pct":
        if previous == 0:
            return ""
        delta = ((current - previous) / previous) * 100.0
        if abs(delta) < 0.1:
            return ""
        improved = delta < 0 if better_when_lower else delta > 0
        direction_up = delta > 0
        return f"{_prefix(improved)}{'▲' if direction_up else '▼'}{trim_decimal(abs(delta), 1)}%"
    delta = current - previous
    if abs(delta) < 0.1:
        return ""
    improved = delta < 0 if better_when_lower else delta > 0
    direction_up = delta > 0
    arrow = "▲" if direction_up else "▼"
    if mode == "pp":
        return f"{_prefix(improved)}{arrow}{trim_decimal(abs(delta), 1)}"
    if mode == "ms":
        return f"{_prefix(improved)}{arrow}{trim_decimal(abs(delta), 1)}"
    return f"{_prefix(improved)}{arrow}{trim_decimal(abs(delta), 1)}"


def _kpi_indicator_neutral(
    *,
    current: float,
    previous: float | None,
    mode: str,
) -> str:
    if previous is None:
        return ""
    if mode == "pct":
        if previous == 0:
            return ""
        delta = ((current - previous) / previous) * 100.0
        if abs(delta) < 0.1:
            return ""
        return f"N:{'▲' if delta > 0 else '▼'}{trim_decimal(abs(delta), 1)}%"
    delta = current - previous
    if abs(delta) < 0.1:
        return ""
    return f"N:{'▲' if delta > 0 else '▼'}{trim_decimal(abs(delta), 1)}"


def _kpi_indicator_pct_with_baseline(
    *,
    current: float,
    previous: float | None,
    better_when_lower: bool = False,
    min_previous: float = 20.0,
) -> str:
    if previous is None or previous < min_previous:
        return ""
    return _kpi_indicator(
        current=current,
        previous=previous,
        mode="pct",
        better_when_lower=better_when_lower,
    )


def _kpi_indicator_count_delta(
    *,
    current: float,
    previous: float | None,
    better_when_lower: bool = False,
    min_baseline: float = 20.0,
    neutral: bool = False,
) -> str:
    if previous is None:
        return ""
    if max(abs(current), abs(previous)) < min_baseline:
        return ""
    delta = current - previous
    if abs(delta) < 1.0:
        return ""
    if neutral:
        return f"N:Δ{'+' if delta > 0 else '-'}{format_count_compact(abs(delta))}"
    improved = delta < 0 if better_when_lower else delta > 0
    return (
        f"{'G:' if improved else 'R:'}{'▲' if delta > 0 else '▼'}{format_count_compact(abs(delta))}"
    )


def _format_cert_expiry_human(soonest: Any, *, as_of: date) -> str:
    return format_date_with_days_from_iso(soonest, as_of=as_of)


def _actions_mitigated_from_top_actions(security: dict[str, Any]) -> int:
    total = 0
    for row in security.get("top_actions") or []:
        action = str(row.get("action") or "").strip().lower()
        if action in _DEFENSIVE_ACTIONS:
            total += as_int(row.get("count"))
    return total


def _threats_mitigated(security: dict[str, Any]) -> int:
    explicit = security.get("mitigated_count")
    if explicit is not None:
        return as_int(explicit)
    return _actions_mitigated_from_top_actions(security)


def _verdict(
    rule_out: ExecutiveRuleOutput,
    warnings: list[str] | None = None,
) -> tuple[str, list[str]]:
    """Aggregate verdict severity from all generated takeaways.

    Returns (verdict, reasons) where verdict is one of:
        "critical" - at least one critical severity rule
        "warning" - at least one warning severity rule (no critical)
        "active" - no critical or warning rules
    """
    critical_reasons = []
    warning_reasons = []

    for line in rule_out.takeaways:
        phrase_data = get_phrase(line.phrase_key, line.state)
        severity = phrase_data.get("severity", "none")

        if severity == "critical":
            critical_reasons.append(line.body)
        elif severity == "warning":
            warning_reasons.append(line.body)

    # Data quality warnings (cache misses, API errors)
    if warnings and len(warnings) > VERDICT_WARN_THRESHOLD:
        warning_reasons.append(f"Missing data for {len(warnings)} metrics")

    if critical_reasons:
        return "critical", critical_reasons
    if warning_reasons:
        return "warning", warning_reasons

    return "active", []


def _get_float(d: dict[str, Any], key: str) -> float | None:
    """Return float value from dict or None if missing/invalid."""
    v = d.get(key)
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def build_executive_summary(
    *,
    zone_id: str = "",
    zone_name: str,
    zone_health: dict[str, Any] | None,
    dns: dict[str, Any] | None,
    http: dict[str, Any] | None,
    security: dict[str, Any] | None,
    cache: dict[str, Any] | None,
    http_adaptive: dict[str, Any] | None = None,
    dns_records: dict[str, Any] | None = None,
    audit: dict[str, Any] | None = None,
    certificates: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
    as_of_date: date | None = None,
    current_period: dict[str, Any] | None = None,
    previous_report: dict[str, Any] | None = None,
    previous_zone: dict[str, Any] | None = None,
    email: dict[str, Any] | None = None,
    disabled_rules: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Build a compact CTO summary object from existing section rollups.

    ``disabled_rules`` entries are either bare phrase keys (letters, digits, underscore) for
    exact match, or any other string treated as a regular expression (``re.search`` on key).
    """
    zh = as_dict(zone_health)
    d = as_dict(dns)
    h = as_dict(http)
    s = as_dict(security)
    c = as_dict(cache)
    ha = as_dict(http_adaptive)
    dr = as_dict(dns_records)
    au = as_dict(audit)
    ce = as_dict(certificates)
    e = as_dict(email)
    warn = list(warnings or [])
    as_of = as_of_date if as_of_date is not None else utc_today()

    mitigated = _threats_mitigated(s)
    sampled_requests = as_int(s.get("http_requests_sampled"))
    not_mitigated = as_int(s.get("not_mitigated_sampled"))

    ssl_mode = _as_str(zh.get("ssl_mode"))
    always_https = _as_str(zh.get("always_https"))
    dnssec_status = _as_str(zh.get("dnssec_status"))
    total_requests = as_int(h.get("total_requests"))
    encrypted_requests = as_int(h.get("encrypted_requests"))
    enc_gap = max(0, total_requests - encrypted_requests)
    enc_gap_pct = (100.0 * enc_gap / total_requests) if total_requests > 0 else 0.0

    msg_filt = ExecutiveMessageFilter.from_entries(list(disabled_rules or []))
    gate = evaluate_comparison_gate(
        current_zone_id=zone_id,
        previous_report=previous_report,
        current_period=as_dict(current_period),
        message_filter=msg_filt,
    )
    current_zone_payload = {
        "zone_name": zone_name,
        "zone_health": zh,
        "http": h,
        "security": s,
        "cache": c,
        "http_adaptive": ha,
        "dns_records": dr,
        "audit": au,
        "certificates": ce,
        "email": e,
    }
    comparison_baseline = None
    if gate.allowed:
        prev_period = as_dict((previous_report or {}).get("report_period"))
        ps = str(prev_period.get("start") or "").strip()
        pe = str(prev_period.get("end") or "").strip()
        if ps and pe:
            comparison_baseline = exec_msg(
                "info",
                "comparison_baseline",
                state="comparison",
                section=SECT_DELTAS,
                filt=msg_filt,
                start=ps,
                end=pe,
            )

    available_streams: dict[str, bool] = {
        "http": http is not None,
        "http_adaptive": http_adaptive is not None,
        "security": security is not None,
        "dns": dns is not None,
        "dns_records": dns_records is not None,
        "cache": cache is not None,
        "email": email is not None,
        "audit": audit is not None,
        "certificates": certificates is not None,
    }
    rule_out = build_executive_rule_output(
        current_zone=current_zone_payload,
        previous_zone=previous_zone,
        comparison_allowed=gate.allowed,
        message_filter=msg_filt,
        gate_warning=gate.blocked_takeaway,
        comparison_baseline=comparison_baseline,
        available_streams=available_streams,
    )
    verdict, reasons = _verdict(rule_out, warn)
    augmented_takeaways = list(rule_out.takeaways)
    if len(warn) > VERDICT_WARN_THRESHOLD:
        missing_data_line = exec_msg(
            "info",
            "missing_data_warning",
            state="observation",
            section=SECT_SIGNALS,
            filt=msg_filt,
            warning_count=len(warn),
        )
        if missing_data_line is not None:
            augmented_takeaways.append(missing_data_line)
    security_posture = build_security_posture_score(rule_out)

    categorized_takeaways = {
        section_key: [
            {
                "phrase_key": line.phrase_key,
                "check_id": line.check_id,
                "service": line.service,
                "nist": list(line.nist),
                "severity": line.severity,
                "message": line.body,
                "display": format_line_with_severity_prefix(
                    line.severity, line.check_id, line.body
                ),
            }
            for line in augmented_takeaways
            if line.section == section_key
        ]
        for section_key in TX_ORDER
    }
    takeaways = [
        str(item["display"]) for bucket in categorized_takeaways.values() for item in bucket
    ]
    actions = [f"[{line.check_id}] {line.body}" for line in rule_out.actions]
    nist_reference = build_nist_reference_rows(
        cast(Sequence[NistSourceLine], augmented_takeaways + list(rule_out.actions))
    )

    mitigation_rate = float(s.get("mitigation_rate_pct") or 0.0)

    p_zone = as_dict(previous_zone) if previous_zone and gate.allowed else {}
    prev_http = as_dict(p_zone.get("http"))
    prev_dns = as_dict(p_zone.get("dns"))
    prev_ha = as_dict(p_zone.get("http_adaptive"))
    prev_sec = as_dict(p_zone.get("security"))
    prev_dr = as_dict(p_zone.get("dns_records"))
    prev_email = as_dict(p_zone.get("email"))

    prev_requests = _get_float(prev_http, "total_requests")
    prev_cache_hit = _get_float(prev_http, "cache_hit_ratio")
    prev_encrypted_requests = _get_float(prev_http, "encrypted_requests")

    prev_qps = _get_float(prev_dns, "average_qps")
    prev_dns_queries = _get_float(prev_dns, "total_queries")

    prev_4xx = _get_float(prev_ha, "status_4xx_rate_pct")
    prev_5xx = _get_float(prev_ha, "status_5xx_rate_pct")
    prev_origin_ms = _get_float(prev_ha, "origin_response_duration_avg_ms")
    prev_p95 = _get_float(prev_ha, "latency_p95_ms")

    prev_mitigated = _get_float(prev_sec, "mitigated_count")
    prev_mitigation_rate = _get_float(prev_sec, "mitigation_rate_pct")

    prev_proxied = _get_float(prev_dr, "proxied_records")
    prev_dns_only = _get_float(prev_dr, "dns_only_records")

    prev_dmarc_pass = _get_float(prev_email, "dmarc_pass_rate_pct")
    prev_delivery_failed_rate = _get_float(prev_email, "delivery_failed_rate_pct")

    kpi_indicators = {
        "traffic.total_requests": _kpi_indicator_pct_with_baseline(
            current=as_float(total_requests), previous=prev_requests
        ),
        "traffic.encrypted_requests": _kpi_indicator_pct_with_baseline(
            current=as_float(encrypted_requests), previous=prev_encrypted_requests
        ),
        "traffic.cache_hit_ratio": _kpi_indicator(
            current=as_float(h.get("cache_hit_ratio")), previous=prev_cache_hit, mode="pp"
        ),
        "security.mitigated_events": _kpi_indicator_count_delta(
            current=as_float(mitigated),
            previous=prev_mitigated,
            neutral=True,
        ),
        "security.mitigation_rate_pct": _kpi_indicator_neutral(
            current=as_float(mitigation_rate),
            previous=prev_mitigation_rate,
            mode="pp",
        ),
        "email.dmarc_pass_rate_pct": _kpi_indicator(
            current=as_float(e.get("dmarc_pass_rate_pct")), previous=prev_dmarc_pass, mode="pp"
        ),
        "email.delivery_failed_rate_pct": _kpi_indicator(
            current=as_float(e.get("delivery_failed_rate_pct")),
            previous=prev_delivery_failed_rate,
            mode="pp",
            better_when_lower=True,
        ),
        "traffic.status_4xx_rate_pct": _kpi_indicator(
            current=as_float(ha.get("status_4xx_rate_pct")),
            previous=prev_4xx,
            mode="pp",
            better_when_lower=True,
        ),
        "traffic.status_5xx_rate_pct": _kpi_indicator(
            current=as_float(ha.get("status_5xx_rate_pct")),
            previous=prev_5xx,
            mode="pp",
            better_when_lower=True,
        ),
        "traffic.origin_response_duration_avg_ms": _kpi_indicator(
            current=as_float(ha.get("origin_response_duration_avg_ms")),
            previous=prev_origin_ms,
            mode="ms",
            better_when_lower=True,
        ),
        "traffic.latency_p95_ms": _kpi_indicator(
            current=as_float(ha.get("latency_p95_ms")),
            previous=prev_p95,
            mode="ms",
            better_when_lower=True,
        ),
        "dns.total_queries": _kpi_indicator_neutral(
            current=as_float(d.get("total_queries")),
            previous=prev_dns_queries,
            mode="pct",
        ),
        "dns.average_qps": _kpi_indicator_neutral(
            current=as_float(d.get("average_qps")), previous=prev_qps, mode="num"
        ),
        "dns_records.proxied_records": _kpi_indicator_count_delta(
            current=as_float(dr.get("proxied_records")),
            previous=prev_proxied,
            min_baseline=3.0,
        ),
        "dns_records.dns_only_records": _kpi_indicator_count_delta(
            current=as_float(dr.get("dns_only_records")),
            previous=prev_dns_only,
            better_when_lower=True,
            min_baseline=3.0,
        ),
    }

    return {
        "zone_name": zone_name,
        "verdict": verdict,
        "verdict_reasons": reasons,
        "security_score": security_posture["score"],
        "security_grade": security_posture["grade"],
        "kpis": {
            "security_posture": {
                "score": security_posture["score"],
                "grade": security_posture["grade"],
                "risk_weight": security_posture["risk_weight"],
            },
            "platform": {
                "zone_status": _as_str(zh.get("zone_status")),
                "ssl_mode": ssl_mode,
                "always_https": always_https,
                "min_tls_version": _as_str(zh.get("min_tls_version")),
                "tls_1_3": _as_str(zh.get("tls_1_3")),
                "browser_check": _as_str(zh.get("browser_check")),
                "email_obfuscation": _as_str(zh.get("email_obfuscation")),
                "opportunistic_encryption": _as_str(zh.get("opportunistic_encryption")),
                "dnssec_status": dnssec_status,
                "ddos_protection": _as_str(zh.get("ddos_protection")),
                "security_rules_active": zh.get("security_rules_active", UNAVAILABLE),
            },
            "traffic": {
                "total_requests": total_requests,
                "total_requests_human": str(h.get("total_requests_human") or "0"),
                "cache_hit_ratio": float(h.get("cache_hit_ratio") or 0.0),
                "encrypted_requests": encrypted_requests,
                "encrypted_requests_human": str(h.get("encrypted_requests_human") or "0"),
                "encrypted_gap_pct": enc_gap_pct,
                "status_4xx_rate_pct": float(ha.get("status_4xx_rate_pct") or 0.0),
                "status_5xx_rate_pct": float(ha.get("status_5xx_rate_pct") or 0.0),
                "latency_p50_ms": ha.get("latency_p50_ms"),
                "latency_p95_ms": ha.get("latency_p95_ms"),
                "origin_response_duration_avg_ms": ha.get("origin_response_duration_avg_ms"),
                "origin_response_duration_avg_ms_daily_mean": ha.get(
                    "origin_response_duration_avg_ms_daily_mean"
                ),
            },
            "security": {
                "mitigated_events": mitigated,
                "mitigated_events_human": format_count_human(mitigated),
                "threats_mitigated": mitigated,
                "threats_mitigated_human": format_count_human(mitigated),
                "analyzed_requests": sampled_requests,
                "analyzed_requests_human": str(s.get("http_requests_sampled_human") or "0"),
                "not_mitigated_sampled": not_mitigated,
                "not_mitigated_sampled_human": str(s.get("not_mitigated_sampled_human") or "0"),
                "mitigation_rate_pct": mitigation_rate,
            },
            "dns": {
                "total_queries": as_int(d.get("total_queries")),
                "total_queries_human": format_count_human(as_int(d.get("total_queries"))),
                "average_qps": float(d.get("average_qps") or 0.0),
            },
            "cache": {
                "cache_hit_ratio": float(
                    c.get("cache_hit_ratio") or h.get("cache_hit_ratio") or 0.0
                ),
                "served_cf_count": as_int(c.get("served_cf_count")),
                "served_origin_count": as_int(c.get("served_origin_count")),
            },
            "dns_records": {
                "unavailable": bool(dr.get("unavailable") is True),
                "total_records": as_int(dr.get("total_records")),
                "proxied_records": as_int(dr.get("proxied_records")),
                "dns_only_records": as_int(dr.get("dns_only_records")),
                "apex_unproxied_a_aaaa": as_int(dr.get("apex_unproxied_a_aaaa")),
                "apex_protection_status": (
                    UNAVAILABLE
                    if dr.get("unavailable") is True
                    else ("exposed" if as_int(dr.get("apex_unproxied_a_aaaa")) > 0 else "proxied")
                ),
            },
            "audit": {
                "unavailable": bool(au.get("unavailable") is True),
                "total_events": as_int(au.get("total_events")),
            },
            "certificates": {
                "unavailable": bool(ce.get("unavailable") is True),
                "total_certificate_packs": as_int(ce.get("total_certificate_packs")),
                "expiring_in_30_days": as_int(ce.get("expiring_in_30_days")),
                "soonest_expiry": ce.get("soonest_expiry"),
                "cert_expires_human": _format_cert_expiry_human(
                    ce.get("soonest_expiry"), as_of=as_of
                ),
            },
            "email": {
                "routing_enabled": bool(e.get("email_routing_enabled")),
                "dns_dmarc_policy": str(e.get("dns_dmarc_policy") or UNAVAILABLE),
                "dmarc_pass_rate_pct": float(e.get("dmarc_pass_rate_pct") or 0.0),
                "total_received": int(e.get("total_received") or 0),
                "delivery_failed": int(e.get("delivery_failed") or 0),
                "delivery_failed_rate_pct": float(e.get("delivery_failed_rate_pct") or 0.0),
            },
        },
        "takeaways": takeaways,
        "takeaways_categorized": categorized_takeaways,
        "actions": actions,
        "nist_reference": nist_reference,
        "kpi_indicators": kpi_indicators,
        "warnings_count": len(warn) + len(categorized_takeaways.get(SECT_RISKS, [])),
        "available_streams": available_streams,
    }
