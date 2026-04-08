"""Shared executive summary derivation for JSON and PDF layers."""

from __future__ import annotations

from datetime import date
from typing import Any

from cloudflare_executive_report.aggregate import format_count_human
from cloudflare_executive_report.dates import format_date_with_days_from_iso, utc_today
from cloudflare_executive_report.executive.rules import (
    build_rule_messages,
    evaluate_comparison_gate,
)

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
    zone_health: dict[str, Any], warnings: list[str], http: dict[str, Any]
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    critical = False

    zone_status = _as_str(zone_health.get("zone_status"))
    if zone_status.lower() != "active":
        reasons.append(f"zone_status={zone_status}")
        critical = True

    if _as_int(http.get("total_requests")) <= 0:
        reasons.append("no_http_traffic")

    if warnings:
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
) -> dict[str, Any]:
    """Build a compact CTO summary object from existing section rollups."""
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
    verdict, reasons = _verdict(zh, warn, h)

    ssl_mode = _as_str(zh.get("ssl_mode"))
    always_https = _as_str(zh.get("always_https"))
    dnssec_status = _as_str(zh.get("dnssec_status"))
    total_requests = _as_int(h.get("total_requests"))
    encrypted_requests = _as_int(h.get("encrypted_requests"))
    enc_gap = max(0, total_requests - encrypted_requests)
    enc_gap_pct = (100.0 * enc_gap / total_requests) if total_requests > 0 else 0.0

    takeaways: list[str] = []

    mitigation_rate = float(s.get("mitigation_rate_pct") or 0.0)

    gate = evaluate_comparison_gate(
        current_zone_id=zone_id,
        previous_report=previous_report,
        current_period=_as_dict(current_period),
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
    rule_buckets = build_rule_messages(
        current_zone=current_zone_payload,
        previous_zone=previous_zone,
        comparison_allowed=gate.allowed,
    )
    if gate.warning is not None:
        rule_buckets["warnings"] = [gate.warning, *rule_buckets.get("warnings", [])]

    takeaway_buckets = ("positive_changes", "warnings", "correlations", "comparisons")
    categorized_takeaways = {
        k: [
            {
                "phrase_key": m.phrase_key,
                "severity": m.severity,
                "message": m.message,
                "display": m.display(),
            }
            for m in v
        ]
        for k in takeaway_buckets
        for v in [rule_buckets.get(k, [])]
    }
    takeaways = [item["display"] for bucket in categorized_takeaways.values() for item in bucket]
    actions = [item.message for item in rule_buckets.get("actions", [])]

    return {
        "zone_name": zone_name,
        "verdict": verdict,
        "verdict_reasons": reasons,
        "kpis": {
            "platform": {
                "zone_status": _as_str(zh.get("zone_status")),
                "ssl_mode": ssl_mode,
                "always_https": always_https,
                "security_level": _as_str(zh.get("security_level")),
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
        "warnings_count": len(warn) + len(categorized_takeaways.get("warnings", [])),
    }
