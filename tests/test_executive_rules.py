from cloudflare_executive_report.executive.phrase_catalog import render_phrase
from cloudflare_executive_report.executive.rules import (
    build_rule_messages,
    evaluate_comparison_gate,
)


def _report_with_zone(zone_id: str, *, start: str, end: str, include_streams: bool = True) -> dict:
    zone = {"zone_id": zone_id}
    if include_streams:
        zone["http"] = {"total_requests": 10}
        zone["security"] = {"mitigated_count": 1}
        zone["dns"] = {"total_queries": 1}
    return {"report_period": {"start": start, "end": end}, "zones": [zone]}


def test_comparison_gate_first_report_phrase():
    gate = evaluate_comparison_gate(
        current_zone_id="z1",
        previous_report=None,
        current_period={"start": "2026-04-01", "end": "2026-04-07"},
    )
    assert gate.allowed is False
    assert gate.warning is not None
    assert gate.warning.message == render_phrase("no_comparison.first_report")


def test_comparison_gate_period_mismatch_phrase():
    prev = _report_with_zone("z1", start="2026-03-01", end="2026-03-30")
    gate = evaluate_comparison_gate(
        current_zone_id="z1",
        previous_report=prev,
        current_period={"start": "2026-04-01", "end": "2026-04-07"},
    )
    assert gate.allowed is False
    assert "Comparison skipped: previous period" in gate.warning.message


def test_correlation_origin_overloaded_uses_exact_phrase():
    current_zone = {
        "zone_health": {},
        "http": {},
        "security": {"mitigation_rate_pct": 0.0},
        "cache": {"cache_hit_ratio": 30.0},
        "http_adaptive": {"status_5xx_rate_pct": 0.8, "origin_response_duration_avg_ms": 600},
        "dns_records": {},
        "audit": {"total_events": 0},
        "certificates": {},
    }
    out = build_rule_messages(
        current_zone=current_zone, previous_zone=None, comparison_allowed=False
    )
    texts = [m.message for m in out["correlations"]]
    assert any(
        "Origin overloaded: high error rate (0.8%) with slow response (600ms)" == t for t in texts
    )
