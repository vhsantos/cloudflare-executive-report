"""Tests verifying that rules only fire for streams present in the report.

When ``available_streams`` restricts which streams were synced, takeaways and
actions for absent streams must not appear. Zone-health rules always run.
"""

from __future__ import annotations

from typing import ClassVar

from cloudflare_executive_report.executive.rules import (
    SECT_RISKS,
    SECT_SIGNALS,
    SECT_WINS,
    build_executive_rule_output,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _zone(*, zone_health: dict | None = None, **streams: dict | None) -> dict:
    """Build a minimal current_zone payload with only the requested streams."""
    base: dict = {
        "zone_health": zone_health
        or {
            "zone_status": "active",
            "ssl_mode": "strict",
            "always_https": "on",
            "dnssec_status": "active",
            "security_level": "medium",
            "ddos_protection": "on",
            "security_rules_active": 1,
        },
    }
    base.update({k: v for k, v in streams.items() if v is not None})
    return base


def _streams(**flags: bool) -> dict[str, bool]:
    """Build an available_streams dict with all streams False by default."""
    defaults = {
        "http": False,
        "http_adaptive": False,
        "security": False,
        "dns": False,
        "dns_records": False,
        "cache": False,
        "email": False,
        "audit": False,
        "certificates": False,
    }
    defaults.update(flags)
    return defaults


def _phrase_keys(out, *, include_actions: bool = False) -> set[str]:
    keys = {ln.phrase_key for ln in out.takeaways}
    if include_actions:
        keys |= {ln.phrase_key for ln in out.actions}
    return keys


# ---------------------------------------------------------------------------
# Email stream gating
# ---------------------------------------------------------------------------


class TestEmailStreamGating:
    """DMARC/SPF/DKIM rules must not appear when email stream is absent."""

    _email_phrase_keys = frozenset(
        {
            "email_dmarc_none",
            "email_dmarc_quarantine",
            "email_spf_missing",
            "email_spf_softfail",
            "email_dkim_missing",
            "email_high_fail_rate",
            "email_routing_drops",
        }
    )

    def _bad_email(self) -> dict:
        return {
            "dns_dmarc_policy": "none",
            "dns_spf_policy": "none",
            "dns_dkim_configured": False,
            "dmarc_pass_rate_pct": 50.0,
            "dropped": 5,
        }

    def test_email_takeaways_absent_when_stream_not_requested(self) -> None:
        out = build_executive_rule_output(
            current_zone=_zone(email=self._bad_email()),
            previous_zone=None,
            comparison_allowed=False,
            available_streams=_streams(),  # email=False
        )
        assert not (self._email_phrase_keys & _phrase_keys(out, include_actions=True))

    def test_email_takeaways_present_when_stream_requested(self) -> None:
        out = build_executive_rule_output(
            current_zone=_zone(email=self._bad_email()),
            previous_zone=None,
            comparison_allowed=False,
            available_streams=_streams(email=True),
        )
        keys = _phrase_keys(out, include_actions=True)
        assert "email_dmarc_none" in keys
        assert "email_dkim_missing" in keys
        assert "email_spf_missing" in keys

    def test_dns_only_report_has_no_email_takeaways(self) -> None:
        """Simulates cf-report report --types dns."""
        out = build_executive_rule_output(
            current_zone=_zone(
                email=self._bad_email(),
                dns={"total_queries": 1000, "average_qps": 1.0},
            ),
            previous_zone=None,
            comparison_allowed=False,
            available_streams=_streams(dns=True, dns_records=True),
        )
        assert not (self._email_phrase_keys & _phrase_keys(out, include_actions=True))


# ---------------------------------------------------------------------------
# Security stream gating
# ---------------------------------------------------------------------------


class TestSecurityStreamGating:
    def test_threat_activity_absent_when_security_not_requested(self) -> None:
        out = build_executive_rule_output(
            current_zone=_zone(security={"mitigation_rate_pct": 99.0}),
            previous_zone=None,
            comparison_allowed=False,
            available_streams=_streams(),
        )
        assert "threat_activity" not in _phrase_keys(out)

    def test_threat_activity_present_when_security_requested(self) -> None:
        out = build_executive_rule_output(
            current_zone=_zone(security={"mitigation_rate_pct": 99.0}),
            previous_zone=None,
            comparison_allowed=False,
            available_streams=_streams(security=True),
        )
        assert "threat_activity" in _phrase_keys(out)


# ---------------------------------------------------------------------------
# HTTP stream gating
# ---------------------------------------------------------------------------


class TestHttpStreamGating:
    def _bad_http_zone(self) -> dict:
        return _zone(
            http={"total_requests": 1_000_000, "total_bandwidth_bytes": 10 * 1024**3},
            http_adaptive={"status_5xx_rate_pct": 5.0, "origin_response_duration_avg_ms": 800},
            cache={"cache_hit_ratio": 5.0},
        )

    def test_origin_signals_absent_when_http_not_requested(self) -> None:
        out = build_executive_rule_output(
            current_zone=self._bad_http_zone(),
            previous_zone=None,
            comparison_allowed=False,
            available_streams=_streams(),
        )
        sig_keys = {ln.phrase_key for ln in out.lines_for_section(SECT_SIGNALS)}
        assert "origin_errors_high" not in sig_keys
        assert "origin_health" not in sig_keys
        assert "cache_efficiency" not in sig_keys

    def test_origin_signals_present_when_http_requested(self) -> None:
        out = build_executive_rule_output(
            current_zone=self._bad_http_zone(),
            previous_zone=None,
            comparison_allowed=False,
            available_streams=_streams(http=True, http_adaptive=True, cache=True),
        )
        sig_keys = {ln.phrase_key for ln in out.lines_for_section(SECT_SIGNALS)}
        assert "origin_errors_high" in sig_keys or "origin_health" in sig_keys


# ---------------------------------------------------------------------------
# Certificate stream gating
# ---------------------------------------------------------------------------


class TestCertificateStreamGating:
    def test_cert_presence_absent_when_certificates_not_requested(self) -> None:
        out = build_executive_rule_output(
            current_zone=_zone(certificates={"total_certificate_packs": 0}),
            previous_zone=None,
            comparison_allowed=False,
            available_streams=_streams(),
        )
        assert "cert_presence" not in _phrase_keys(out, include_actions=True)

    def test_cert_expiry_present_when_certificates_requested(self) -> None:
        out = build_executive_rule_output(
            current_zone=_zone(
                certificates={
                    "total_certificate_packs": 1,
                    "expiring_in_30_days": 5,
                    "soonest_expiry": "2026-05-15T00:00:00Z",
                }
            ),
            previous_zone=None,
            comparison_allowed=False,
            available_streams=_streams(certificates=True),
        )
        assert "cert_expire_30" in _phrase_keys(out, include_actions=True)


# ---------------------------------------------------------------------------
# Audit stream gating
# ---------------------------------------------------------------------------


class TestAuditStreamGating:
    def test_audit_activity_absent_when_audit_not_requested(self) -> None:
        out = build_executive_rule_output(
            current_zone=_zone(audit={"total_events": 999}),
            previous_zone=None,
            comparison_allowed=False,
            available_streams=_streams(),
        )
        assert "audit_activity" not in _phrase_keys(out, include_actions=True)

    def test_audit_activity_present_when_audit_requested(self) -> None:
        out = build_executive_rule_output(
            current_zone=_zone(audit={"total_events": 999}),
            previous_zone=None,
            comparison_allowed=False,
            available_streams=_streams(audit=True),
        )
        assert "audit_activity" in _phrase_keys(out, include_actions=True)


# ---------------------------------------------------------------------------
# Zone-health rules always run
# ---------------------------------------------------------------------------


class TestZoneHealthAlwaysRuns:
    """Zone-health posture rules must fire even with no streams requested."""

    def test_ssl_mode_off_risk_absent_with_no_edge_traffic_and_no_streams(self) -> None:
        out = build_executive_rule_output(
            current_zone=_zone(
                zone_health={
                    "ssl_mode": "off",
                    "always_https": "on",
                    "dnssec_status": "active",
                    "security_rules_active": 1,
                    "ddos_protection": "on",
                }
            ),
            previous_zone=None,
            comparison_allowed=False,
            available_streams=_streams(),  # nothing requested
        )
        risk_keys = {ln.phrase_key for ln in out.lines_for_section(SECT_RISKS)}
        assert "ssl_mode_off" not in risk_keys

    def test_dnssec_risk_fires_with_no_streams(self) -> None:
        out = build_executive_rule_output(
            current_zone=_zone(
                zone_health={
                    "ssl_mode": "strict",
                    "always_https": "on",
                    "dnssec_status": "off",
                    "security_rules_active": 1,
                    "ddos_protection": "on",
                }
            ),
            previous_zone=None,
            comparison_allowed=False,
            available_streams=_streams(),
        )
        risk_keys = {ln.phrase_key for ln in out.lines_for_section(SECT_RISKS)}
        assert "dnssec" in risk_keys


# ---------------------------------------------------------------------------
# Comparison delta gating
# ---------------------------------------------------------------------------


class TestComparisonDeltaGating:
    """Delta rules respect available_streams: only traffic/security/latency deltas
    emit when their respective streams are present."""

    _prev_report_period: ClassVar[dict[str, str]] = {"start": "2026-03-25", "end": "2026-03-31"}
    _curr_period: ClassVar[dict[str, str]] = {"start": "2026-04-01", "end": "2026-04-07"}

    def _prev_zone(self) -> dict:
        return {
            "zone_id": "z1",
            "http": {"total_requests": 1000, "cache_hit_ratio": 50.0},
            "security": {"mitigated_count": 10},
            "http_adaptive": {"origin_response_duration_avg_ms": 200.0},
            "dns_records": {"apex_unproxied_a_aaaa": 0},
            "zone_health": {"ssl_mode": "strict", "dnssec_status": "active"},
            "email": {"dns_dmarc_policy": "none"},
        }

    def _curr_zone(self) -> dict:
        return _zone(
            http={"total_requests": 2000, "cache_hit_ratio": 50.0},
            security={"mitigated_count": 100},
            http_adaptive={"origin_response_duration_avg_ms": 200.0},
            dns_records={"apex_unproxied_a_aaaa": 0},
            email={"dns_dmarc_policy": "reject"},
        )

    def test_traffic_delta_absent_when_http_not_requested(self) -> None:
        out = build_executive_rule_output(
            current_zone=self._curr_zone(),
            previous_zone=self._prev_zone(),
            comparison_allowed=True,
            available_streams=_streams(),  # http=False
        )
        delta_keys = {ln.phrase_key for ln in out.lines_for_section("deltas")}
        win_keys = {ln.phrase_key for ln in out.lines_for_section(SECT_WINS)}
        assert "traffic_up" not in delta_keys
        assert "traffic_up" not in win_keys

    def test_traffic_delta_present_when_http_requested(self) -> None:
        out = build_executive_rule_output(
            current_zone=self._curr_zone(),
            previous_zone=self._prev_zone(),
            comparison_allowed=True,
            available_streams=_streams(http=True),
        )
        delta_keys = {ln.phrase_key for ln in out.lines_for_section("deltas")}
        win_keys = {ln.phrase_key for ln in out.lines_for_section(SECT_WINS)}
        assert "traffic_up" in delta_keys or "traffic_up" in win_keys

    def test_email_wins_absent_when_email_not_requested(self) -> None:
        out = build_executive_rule_output(
            current_zone=self._curr_zone(),
            previous_zone=self._prev_zone(),
            comparison_allowed=True,
            available_streams=_streams(),  # email=False
        )
        win_keys = {ln.phrase_key for ln in out.lines_for_section(SECT_WINS)}
        assert "email_dmarc_reject" not in win_keys

    def test_email_wins_present_when_email_requested(self) -> None:
        out = build_executive_rule_output(
            current_zone=self._curr_zone(),
            previous_zone=self._prev_zone(),
            comparison_allowed=True,
            available_streams=_streams(email=True),
        )
        win_keys = {ln.phrase_key for ln in out.lines_for_section(SECT_WINS)}
        assert "email_dmarc_reject" in win_keys


# ---------------------------------------------------------------------------
# Backward compatibility: no available_streams means all rules run
# ---------------------------------------------------------------------------


class TestBackwardCompatibility:
    """Callers that do not pass available_streams get the old all-streams behaviour."""

    def test_email_rules_fire_without_available_streams_arg(self) -> None:
        out = build_executive_rule_output(
            current_zone=_zone(
                email={
                    "dns_dmarc_policy": "none",
                    "dns_spf_policy": "none",
                    "dns_dkim_configured": False,
                }
            ),
            previous_zone=None,
            comparison_allowed=False,
            # available_streams intentionally omitted
        )
        assert "email_dmarc_none" in _phrase_keys(out, include_actions=True)
