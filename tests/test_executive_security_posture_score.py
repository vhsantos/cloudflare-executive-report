"""Tests for risks-only security posture score on executive takeaways."""

from cloudflare_executive_report.executive.rules import (
    SECT_DELTAS,
    SECT_RISKS,
    SECT_SIGNALS,
    SECT_WINS,
    ExecutiveLine,
    ExecutiveRuleOutput,
)
from cloudflare_executive_report.executive.summary import build_security_posture_score


def _line(
    phrase_key: str,
    *,
    state: str,
    section: str,
    severity: str = "warning",
) -> ExecutiveLine:
    return ExecutiveLine(
        phrase_key=phrase_key,
        state=state,
        check_id="TST-000",
        service="Test",
        nist=(),
        severity=severity,
        body="body",
        section=section,
    )


def test_security_posture_score_no_takeaways_is_perfect() -> None:
    out = build_security_posture_score(ExecutiveRuleOutput(takeaways=(), actions=()))
    assert out["score"] == 100.0
    assert out["grade"] == "A+"
    assert out["risk_weight"] == 0


def test_security_posture_score_single_ssl_risk() -> None:
    takeaways = (_line("ssl_mode_off", state="risk", section=SECT_RISKS),)
    out = build_security_posture_score(ExecutiveRuleOutput(takeaways=takeaways, actions=()))
    assert out["risk_weight"] == 10
    assert out["score"] == 83.3
    assert out["grade"] == "B"


def test_security_posture_score_deltas_and_signals_ignored() -> None:
    takeaways = (
        _line("ssl_mode_off", state="risk", section=SECT_RISKS),
        _line("comparison_baseline", state="comparison", section=SECT_DELTAS),
        _line("threat_activity", state="observation", section=SECT_SIGNALS),
    )
    out = build_security_posture_score(ExecutiveRuleOutput(takeaways=takeaways, actions=()))
    assert out["risk_weight"] == 10
    assert out["score"] == 83.3


def test_security_posture_score_signals_only_full_score() -> None:
    takeaways = (_line("threat_activity", state="observation", section=SECT_SIGNALS),)
    out = build_security_posture_score(ExecutiveRuleOutput(takeaways=takeaways, actions=()))
    assert out["risk_weight"] == 0
    assert out["score"] == 100.0
    assert out["grade"] == "A+"


def test_security_posture_score_wins_ignored() -> None:
    takeaways = (_line("traffic_up", state="win", section=SECT_WINS),)
    out = build_security_posture_score(ExecutiveRuleOutput(takeaways=takeaways, actions=()))
    assert out["risk_weight"] == 0
    assert out["score"] == 100.0
    assert out["grade"] == "A+"


def test_security_posture_score_ssl_and_waf_example() -> None:
    takeaways = (
        _line("ssl_mode_off", state="risk", section=SECT_RISKS),
        _line("waf", state="risk", section=SECT_RISKS),
    )
    out = build_security_posture_score(ExecutiveRuleOutput(takeaways=takeaways, actions=()))
    assert out["risk_weight"] == 19
    assert out["score"] == 68.3
    assert out["grade"] == "C+"


def test_security_posture_score_ssl_waf_dnssec_example() -> None:
    takeaways = (
        _line("ssl_mode_off", state="risk", section=SECT_RISKS),
        _line("waf", state="risk", section=SECT_RISKS),
        _line("dnssec", state="risk", section=SECT_RISKS),
    )
    out = build_security_posture_score(ExecutiveRuleOutput(takeaways=takeaways, actions=()))
    assert out["risk_weight"] == 26
    assert out["score"] == 56.7
    assert out["grade"] == "C"


def test_security_posture_score_saturated_risk_is_zero() -> None:
    takeaways = tuple(_line("ssl_mode_off", state="risk", section=SECT_RISKS) for _ in range(6))
    out = build_security_posture_score(ExecutiveRuleOutput(takeaways=takeaways, actions=()))
    assert out["risk_weight"] == 60
    assert out["score"] == 0.0
    assert out["grade"] == "F"


def test_security_posture_score_over_reference_caps_at_zero() -> None:
    takeaways = tuple(_line("ssl_mode_off", state="risk", section=SECT_RISKS) for _ in range(7))
    out = build_security_posture_score(ExecutiveRuleOutput(takeaways=takeaways, actions=()))
    assert out["risk_weight"] == 70
    assert out["score"] == 0.0
