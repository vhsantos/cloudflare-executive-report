"""Shared executive summary derivation for JSON and PDF layers."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Any

from cloudflare_executive_report.common.constants import (
    SECURITY_POSTURE_REFERENCE_RISK_WEIGHT,
    VERDICT_WARN_THRESHOLD,
)
from cloudflare_executive_report.common.dates import format_date_with_days_from_iso, utc_today
from cloudflare_executive_report.common.formatting import (
    format_count_compact,
    format_count_human,
    trim_decimal,
)
from cloudflare_executive_report.executive.nist_catalog import build_nist_reference_rows
from cloudflare_executive_report.executive.phrase_catalog import (
    format_line_with_severity_prefix,
    get_phrase,
)
from cloudflare_executive_report.executive.rules import (
    SECT_DELTAS,
    SECT_RISKS,
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


_DEFENSIVE_ACTIONS = frozenset(
    {
        "block",
        "managed_challenge",
        "jschallenge",
        "interactive_challenge",
        "challenge",
    }
)


def _as_dict(v: Any) -> dict[str, Any]:
    return v if isinstance(v, dict) else {}


def _as_str(v: Any, *, default: str = "unavailable") -> str:
    s = str(v).strip() if v is not None else ""
    return s if s else default


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
        if not isinstance(row, dict):
            continue
        action = str(row.get("action") or "").strip().lower()
        if action in _DEFENSIVE_ACTIONS:
            total += _as_int(row.get("count"))
    return total


def _threats_mitigated(security: dict[str, Any]) -> int:
    explicit = security.get("mitigated_count")
    if explicit is not None:
        return _as_int(explicit)
    return _actions_mitigated_from_top_actions(security)


def _verdict(
    zone_health: dict[str, Any],
    warnings: list[str],
    http: dict[str, Any],
    dns_records: dict[str, Any],
) -> tuple[str, list[str]]:
    """Classify zone rollup health for the executive verdict KPI."""
    reasons: list[str] = []
    critical = False

    zone_status = _as_str(zone_health.get("zone_status"))
    if zone_status.lower() != "active":
        reasons.append(f"zone_status={zone_status}")
        critical = True

    has_proxied = _as_int(dns_records.get("proxied_records")) > 0
    has_http_traffic = _as_int(http.get("total_requests")) > 0
    if has_proxied and not has_http_traffic:
        reasons.append("no_http_traffic")

    if len(warnings) > VERDICT_WARN_THRESHOLD:
        reasons.append("warnings_present")

    if critical:
        return "critical", reasons
    if reasons:
        return "warning", reasons
    return "healthy", reasons


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
    disabled_rules: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Build a compact CTO summary object from existing section rollups.

    ``disabled_rules`` entries are either bare phrase keys (letters, digits, underscore) for
    exact match, or any other string treated as a regular expression (``re.search`` on key).
    """
    zh = _as_dict(zone_health)
    d = _as_dict(dns)
    h = _as_dict(http)
    s = _as_dict(security)
    c = _as_dict(cache)
    ha = _as_dict(http_adaptive)
    dr = _as_dict(dns_records)
    au = _as_dict(audit)
    ce = _as_dict(certificates)
    warn = list(warnings or [])
    as_of = as_of_date if as_of_date is not None else utc_today()

    mitigated = _threats_mitigated(s)
    sampled_requests = _as_int(s.get("http_requests_sampled"))
    not_mitigated = _as_int(s.get("not_mitigated_sampled"))
    verdict, reasons = _verdict(zh, warn, h, dr)

    ssl_mode = _as_str(zh.get("ssl_mode"))
    always_https = _as_str(zh.get("always_https"))
    dnssec_status = _as_str(zh.get("dnssec_status"))
    total_requests = _as_int(h.get("total_requests"))
    encrypted_requests = _as_int(h.get("encrypted_requests"))
    enc_gap = max(0, total_requests - encrypted_requests)
    enc_gap_pct = (100.0 * enc_gap / total_requests) if total_requests > 0 else 0.0

    takeaways: list[str] = []

    mitigation_rate = float(s.get("mitigation_rate_pct") or 0.0)

    msg_filt = ExecutiveMessageFilter.from_entries(list(disabled_rules or []))
    gate = evaluate_comparison_gate(
        current_zone_id=zone_id,
        previous_report=previous_report,
        current_period=_as_dict(current_period),
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
    }
    comparison_baseline = None
    if gate.allowed:
        prev_period = _as_dict((previous_report or {}).get("report_period"))
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

    rule_out = build_executive_rule_output(
        current_zone=current_zone_payload,
        previous_zone=previous_zone,
        comparison_allowed=gate.allowed,
        message_filter=msg_filt,
        gate_warning=gate.blocked_takeaway,
        comparison_baseline=comparison_baseline,
    )
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
            for line in rule_out.lines_for_section(section_key)
        ]
        for section_key in TX_ORDER
    }
    takeaways = [item["display"] for bucket in categorized_takeaways.values() for item in bucket]
    actions = [f"[{line.check_id}] {line.body}" for line in rule_out.actions]
    nist_reference = build_nist_reference_rows(list(rule_out.takeaways) + list(rule_out.actions))
    prev_http = _as_dict(previous_zone.get("http")) if previous_zone else {}
    prev_dns = _as_dict(previous_zone.get("dns")) if previous_zone else {}
    prev_ha = _as_dict(previous_zone.get("http_adaptive")) if previous_zone else {}
    prev_sec = _as_dict(previous_zone.get("security")) if previous_zone else {}
    prev_dr = _as_dict(previous_zone.get("dns_records")) if previous_zone else {}
    prev_requests = (
        _as_float(prev_http.get("total_requests")) if previous_zone and gate.allowed else None
    )
    prev_cache_hit = (
        _as_float(prev_http.get("cache_hit_ratio")) if previous_zone and gate.allowed else None
    )
    prev_4xx = (
        _as_float(prev_ha.get("status_4xx_rate_pct")) if previous_zone and gate.allowed else None
    )
    prev_origin_ms = (
        _as_float(prev_ha.get("origin_response_duration_avg_ms"))
        if previous_zone and gate.allowed
        else None
    )
    prev_qps = _as_float(prev_dns.get("average_qps")) if previous_zone and gate.allowed else None
    prev_encrypted_requests = (
        _as_float(prev_http.get("encrypted_requests")) if previous_zone and gate.allowed else None
    )
    prev_mitigated = (
        _as_float(prev_sec.get("mitigated_count")) if previous_zone and gate.allowed else None
    )
    prev_mitigation_rate = (
        _as_float(prev_sec.get("mitigation_rate_pct")) if previous_zone and gate.allowed else None
    )
    prev_5xx = (
        _as_float(prev_ha.get("status_5xx_rate_pct")) if previous_zone and gate.allowed else None
    )
    prev_dns_queries = (
        _as_float(prev_dns.get("total_queries")) if previous_zone and gate.allowed else None
    )
    prev_proxied = (
        _as_float(prev_dr.get("proxied_records")) if previous_zone and gate.allowed else None
    )
    prev_dns_only = (
        _as_float(prev_dr.get("dns_only_records")) if previous_zone and gate.allowed else None
    )
    prev_p95 = _as_float(prev_ha.get("latency_p95_ms")) if previous_zone and gate.allowed else None
    kpi_indicators = {
        "traffic.total_requests": _kpi_indicator_pct_with_baseline(
            current=_as_float(total_requests), previous=prev_requests
        ),
        "traffic.encrypted_requests": _kpi_indicator_pct_with_baseline(
            current=_as_float(encrypted_requests), previous=prev_encrypted_requests
        ),
        "traffic.cache_hit_ratio": _kpi_indicator(
            current=_as_float(h.get("cache_hit_ratio")), previous=prev_cache_hit, mode="pp"
        ),
        "security.mitigated_events": _kpi_indicator_count_delta(
            current=_as_float(mitigated),
            previous=prev_mitigated,
            neutral=True,
        ),
        "security.mitigation_rate_pct": _kpi_indicator_neutral(
            current=_as_float(mitigation_rate),
            previous=prev_mitigation_rate,
            mode="pp",
        ),
        "traffic.status_4xx_rate_pct": _kpi_indicator(
            current=_as_float(ha.get("status_4xx_rate_pct")),
            previous=prev_4xx,
            mode="pp",
            better_when_lower=True,
        ),
        "traffic.status_5xx_rate_pct": _kpi_indicator(
            current=_as_float(ha.get("status_5xx_rate_pct")),
            previous=prev_5xx,
            mode="pp",
            better_when_lower=True,
        ),
        "traffic.origin_response_duration_avg_ms": _kpi_indicator(
            current=_as_float(ha.get("origin_response_duration_avg_ms")),
            previous=prev_origin_ms,
            mode="ms",
            better_when_lower=True,
        ),
        "traffic.latency_p95_ms": _kpi_indicator(
            current=_as_float(ha.get("latency_p95_ms")),
            previous=prev_p95,
            mode="ms",
            better_when_lower=True,
        ),
        "dns.total_queries": _kpi_indicator_neutral(
            current=_as_float(d.get("total_queries")),
            previous=prev_dns_queries,
            mode="pct",
        ),
        "dns.average_qps": _kpi_indicator_neutral(
            current=_as_float(d.get("average_qps")), previous=prev_qps, mode="num"
        ),
        "dns_records.proxied_records": _kpi_indicator_count_delta(
            current=_as_float(dr.get("proxied_records")),
            previous=prev_proxied,
            min_baseline=3.0,
        ),
        "dns_records.dns_only_records": _kpi_indicator_count_delta(
            current=_as_float(dr.get("dns_only_records")),
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
                "security_rules_active": zh.get("security_rules_active", "unavailable"),
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
                "total_queries": _as_int(d.get("total_queries")),
                "total_queries_human": format_count_human(_as_int(d.get("total_queries"))),
                "average_qps": float(d.get("average_qps") or 0.0),
            },
            "cache": {
                "cache_hit_ratio": float(
                    c.get("cache_hit_ratio") or h.get("cache_hit_ratio") or 0.0
                ),
                "served_cf_count": _as_int(c.get("served_cf_count")),
                "served_origin_count": _as_int(c.get("served_origin_count")),
            },
            "dns_records": {
                "unavailable": bool(dr.get("unavailable") is True),
                "total_records": _as_int(dr.get("total_records")),
                "proxied_records": _as_int(dr.get("proxied_records")),
                "dns_only_records": _as_int(dr.get("dns_only_records")),
                "apex_unproxied_a_aaaa": _as_int(dr.get("apex_unproxied_a_aaaa")),
                "apex_protection_status": (
                    "unavailable"
                    if dr.get("unavailable") is True
                    else ("exposed" if _as_int(dr.get("apex_unproxied_a_aaaa")) > 0 else "proxied")
                ),
            },
            "audit": {
                "unavailable": bool(au.get("unavailable") is True),
                "total_events": _as_int(au.get("total_events")),
            },
            "certificates": {
                "unavailable": bool(ce.get("unavailable") is True),
                "total_certificate_packs": _as_int(ce.get("total_certificate_packs")),
                "expiring_in_30_days": _as_int(ce.get("expiring_in_30_days")),
                "soonest_expiry": ce.get("soonest_expiry"),
                "cert_expires_human": _format_cert_expiry_human(
                    ce.get("soonest_expiry"), as_of=as_of
                ),
            },
        },
        "takeaways": takeaways,
        "takeaways_categorized": categorized_takeaways,
        "actions": actions,
        "nist_reference": nist_reference,
        "kpi_indicators": kpi_indicators,
        "warnings_count": len(warn) + len(categorized_takeaways.get(SECT_RISKS, [])),
    }
