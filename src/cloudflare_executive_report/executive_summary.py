"""Shared executive summary derivation for JSON and PDF layers."""

from __future__ import annotations

from typing import Any

from cloudflare_executive_report.aggregate import format_count_human

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
    zone_name: str,
    zone_health: dict[str, Any] | None,
    dns: dict[str, Any] | None,
    http: dict[str, Any] | None,
    security: dict[str, Any] | None,
    cache: dict[str, Any] | None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    """Build a compact CTO summary object from existing section rollups."""
    zh = _as_dict(zone_health)
    d = _as_dict(dns)
    h = _as_dict(http)
    s = _as_dict(security)
    c = _as_dict(cache)
    warn = list(warnings or [])

    mitigated = _threats_mitigated(s)
    sampled_requests = _as_int(s.get("http_requests_sampled"))
    not_mitigated = _as_int(s.get("not_mitigated_sampled"))
    verdict, reasons = _verdict(zh, warn, h)

    ssl_mode = _as_str(zh.get("ssl_mode"))
    always_https = _as_str(zh.get("always_https"))
    dnssec_status = _as_str(zh.get("dnssec_status"))

    takeaways: list[str] = []
    actions: list[str] = []

    takeaways.append(
        f"Traffic: {format_count_human(_as_int(h.get('total_requests')))} requests in period."
    )
    mitigation_rate = float(s.get("mitigation_rate_pct") or 0.0)
    takeaways.append(
        f"Security: {format_count_human(mitigated)} threats were blocked or challenged "
        f"({mitigation_rate:.1f}% of traffic)."
    )
    takeaways.append(
        f"DNS: {format_count_human(_as_int(d.get('total_queries')))} queries at "
        f"{float(d.get('average_qps') or 0.0):.3f} qps average."
    )

    if always_https.lower() != "on":
        actions.append("Enable Always Use HTTPS at zone level.")
    if dnssec_status.lower() in {"disabled", "off", "unavailable"}:
        actions.append("Review DNSSEC configuration and enable if policy requires it.")
    if ssl_mode.lower() not in {"strict", "full_strict"}:
        actions.append("Review SSL mode and target Strict for origin validation.")
    if _as_int(zh.get("security_rules_active")) == 0:
        actions.append("Review firewall/rate-limit posture and activate baseline rules.")
    if not actions:
        actions.append("Maintain current baseline and monitor daily warning signals.")

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
                "total_requests": _as_int(h.get("total_requests")),
                "total_requests_human": str(h.get("total_requests_human") or "0"),
                "cache_hit_ratio": float(h.get("cache_hit_ratio") or 0.0),
                "encrypted_requests": _as_int(h.get("encrypted_requests")),
                "encrypted_requests_human": str(h.get("encrypted_requests_human") or "0"),
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
        },
        "takeaways": takeaways,
        "actions": actions[:3],
        "warnings_count": len(warn),
    }
