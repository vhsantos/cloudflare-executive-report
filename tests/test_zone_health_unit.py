"""Unit tests for zone_health.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from cloudflare import PermissionDeniedError

from cloudflare_executive_report.zone_health import (
    UNAVAILABLE,
    _dnssec_status,
    _setting_value,
    fetch_zone_health,
)


def test_setting_value_success() -> None:
    sdk = MagicMock()
    mock_resp = MagicMock()
    mock_resp.model_dump.return_value = {"value": "on"}
    sdk.zones.settings.get.return_value = mock_resp

    warnings = []
    val = _setting_value(sdk, "z1", "ssl", warnings, label="SSL")
    assert val == "on"
    assert not warnings


def test_setting_value_permission_denied() -> None:
    sdk = MagicMock()
    sdk.zones.settings.get.side_effect = PermissionDeniedError(
        message="Denied", response=MagicMock(), body={}
    )

    warnings = []
    val = _setting_value(sdk, "z1", "ssl", warnings, label="SSL")
    assert val == UNAVAILABLE
    assert "permission denied" in warnings[0]


def test_dnssec_status_disabled() -> None:
    sdk = MagicMock()
    sdk.dns.dnssec.get.return_value = None

    warnings = []
    val = _dnssec_status(sdk, "z1", warnings)
    assert val == "disabled"


@patch("cloudflare_executive_report.zone_health._setting_value")
@patch("cloudflare_executive_report.zone_health._dnssec_status")
@patch("cloudflare_executive_report.zone_health._ruleset_rules_active_count")
def test_fetch_zone_health_flow(
    mock_rules: MagicMock,
    mock_dnssec: MagicMock,
    mock_set: MagicMock,
) -> None:
    client = MagicMock()

    mock_set.return_value = "on"
    mock_dnssec.return_value = "active"
    mock_rules.return_value = 5

    res, _warns = fetch_zone_health(client, "z1", "n1", skip=False)
    assert res["ssl_mode"] == "on"
    assert res["dnssec_status"] == "active"
    assert res["security_rules_active"] == 5
