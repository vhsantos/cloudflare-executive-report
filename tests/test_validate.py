"""Unit tests for token permission validation."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from cloudflare import APIStatusError

from cloudflare_executive_report.cf_client import (
    CloudflareAPIError,
    CloudflareAuthError,
    CloudflareRateLimitError,
)
from cloudflare_executive_report.validate.consts import (
    ACCOUNT_AUDIT_READ,
    ACCOUNT_SETTINGS_READ,
    ALL_PERMISSIONS,
    ZONE_ANALYTICS_READ,
    ZONE_DNS_READ,
    ZONE_READ,
    ZONE_SETTINGS_READ,
)
from cloudflare_executive_report.validate.runner import (
    STATUS_ERROR,
    STATUS_MISSING,
    STATUS_NOT_FOUND,
    STATUS_OK,
    STATUS_RATE_LIMITED,
    STATUS_SKIPPED,
    PermissionResult,
    _resolve_account_id,
    validate_token_permissions,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_client(
    *,
    first_account_id: str | None = "acct-123",
    probe_side_effects: dict[str, Exception | None] | None = None,
) -> MagicMock:
    """Build a mock CloudflareClient with sensible defaults."""
    client = MagicMock()
    client.get_first_account_id.return_value = first_account_id

    if probe_side_effects:
        for attr_path, exc in probe_side_effects.items():
            parts = attr_path.split(".")
            obj = client
            for part in parts[:-1]:
                obj = getattr(obj, part)
            if exc is not None:
                getattr(obj, parts[-1]).side_effect = exc
    return client


# ---------------------------------------------------------------------------
# PermissionResult - unit tests
# ---------------------------------------------------------------------------


def test_permission_result_ok_property() -> None:
    result = PermissionResult(permission=ZONE_READ, status=STATUS_OK)
    assert result.ok is True
    assert result.skipped is False


def test_permission_result_missing_not_ok() -> None:
    result = PermissionResult(permission=ZONE_READ, status=STATUS_MISSING, message="403")
    assert result.ok is False
    assert result.skipped is False


def test_permission_result_skipped_property() -> None:
    result = PermissionResult(permission=ZONE_READ, status=STATUS_SKIPPED)
    assert result.skipped is True
    assert result.ok is False


def test_permission_result_is_frozen() -> None:
    result = PermissionResult(permission=ZONE_READ, status=STATUS_OK)
    with pytest.raises((AttributeError, TypeError)):
        result.status = STATUS_MISSING  # type: ignore[misc]


def test_permission_result_used_by_defaults_empty() -> None:
    result = PermissionResult(permission=ZONE_READ, status=STATUS_OK)
    assert result.used_by == ()


# ---------------------------------------------------------------------------
# validate_token_permissions - happy path
# ---------------------------------------------------------------------------


def test_all_permissions_ok_when_probes_succeed() -> None:
    client = _make_client()
    results = validate_token_permissions(
        client,
        zone_id="zone-abc",
        permissions=[ZONE_READ, ZONE_DNS_READ],
        probe_delay_seconds=0,
    )
    assert len(results) == 2
    assert all(r.ok for r in results)


def test_returns_one_result_per_permission() -> None:
    client = _make_client()
    results = validate_token_permissions(
        client,
        zone_id="zone-abc",
        permissions=list(ALL_PERMISSIONS),
        probe_delay_seconds=0,
    )
    assert len(results) == len(ALL_PERMISSIONS)


def test_result_order_matches_permissions_input() -> None:
    client = _make_client()
    perms = [ZONE_DNS_READ, ZONE_READ, ZONE_ANALYTICS_READ]
    results = validate_token_permissions(
        client,
        zone_id="zone-abc",
        permissions=perms,
        probe_delay_seconds=0,
    )
    assert [r.permission for r in results] == perms


# ---------------------------------------------------------------------------
# validate_token_permissions - MISSING / auth failures
# ---------------------------------------------------------------------------


def test_auth_error_yields_missing_status() -> None:
    client = _make_client(probe_side_effects={"get_zone": CloudflareAuthError("403 Forbidden")})
    results = validate_token_permissions(
        client,
        zone_id="zone-abc",
        permissions=[ZONE_READ],
        probe_delay_seconds=0,
    )
    assert results[0].status == STATUS_MISSING
    assert "403" in results[0].message


def test_api_error_with_403_yields_missing_status() -> None:
    client = _make_client(
        probe_side_effects={"get_zone": CloudflareAPIError("403 permission denied")}
    )
    results = validate_token_permissions(
        client,
        zone_id="zone-abc",
        permissions=[ZONE_READ],
        probe_delay_seconds=0,
    )
    assert results[0].status == STATUS_MISSING


def test_rate_limit_yields_rate_limited_status() -> None:
    client = _make_client(probe_side_effects={"get_zone": CloudflareRateLimitError("429")})
    results = validate_token_permissions(
        client,
        zone_id="zone-abc",
        permissions=[ZONE_READ],
        probe_delay_seconds=0,
    )
    assert results[0].status == STATUS_RATE_LIMITED


def test_404_api_error_yields_not_found_status() -> None:
    client = _make_client(probe_side_effects={"get_zone": CloudflareAPIError("404 not found")})
    results = validate_token_permissions(
        client,
        zone_id="zone-abc",
        permissions=[ZONE_READ],
        probe_delay_seconds=0,
    )
    assert results[0].status == STATUS_NOT_FOUND


def test_unexpected_exception_yields_error_status() -> None:
    client = _make_client(probe_side_effects={"get_zone": RuntimeError("unexpected")})
    results = validate_token_permissions(
        client,
        zone_id="zone-abc",
        permissions=[ZONE_READ],
        probe_delay_seconds=0,
    )
    assert results[0].status == STATUS_ERROR
    assert "unexpected" in results[0].message


# ---------------------------------------------------------------------------
# validate_token_permissions - SKIPPED when targets missing
# ---------------------------------------------------------------------------


def test_zone_permissions_skipped_when_no_zone_id() -> None:
    client = _make_client()
    results = validate_token_permissions(
        client,
        zone_id=None,
        permissions=[ZONE_READ, ZONE_DNS_READ],
        probe_delay_seconds=0,
    )
    assert all(r.status == STATUS_SKIPPED for r in results)
    assert all(not r.is_account_scoped for r in results)


def test_account_permissions_skipped_when_no_account_found() -> None:
    client = _make_client(first_account_id=None)
    results = validate_token_permissions(
        client,
        zone_id="zone-abc",
        permissions=[ACCOUNT_AUDIT_READ, ACCOUNT_SETTINGS_READ],
        probe_delay_seconds=0,
    )
    assert all(r.status == STATUS_SKIPPED for r in results)
    assert all(r.is_account_scoped for r in results)


def test_account_id_resolved_only_once_for_multiple_account_permissions() -> None:
    """get_first_account_id must be called exactly once even with multiple account permissions."""
    client = _make_client()
    validate_token_permissions(
        client,
        zone_id="zone-abc",
        permissions=[ACCOUNT_AUDIT_READ, ACCOUNT_SETTINGS_READ],
        probe_delay_seconds=0,
    )
    client.get_first_account_id.assert_called_once()


def test_account_id_not_fetched_when_only_zone_permissions_requested() -> None:
    client = _make_client()
    validate_token_permissions(
        client,
        zone_id="zone-abc",
        permissions=[ZONE_READ, ZONE_DNS_READ],
        probe_delay_seconds=0,
    )
    client.get_first_account_id.assert_not_called()


# ---------------------------------------------------------------------------
# validate_token_permissions - mixed zone + account
# ---------------------------------------------------------------------------


def test_mixed_permissions_correct_scoping() -> None:
    client = _make_client()
    results = validate_token_permissions(
        client,
        zone_id="zone-abc",
        permissions=[ZONE_READ, ACCOUNT_AUDIT_READ],
        probe_delay_seconds=0,
    )
    assert len(results) == 2
    assert results[0].is_account_scoped is False
    assert results[1].is_account_scoped is True


# ---------------------------------------------------------------------------
# _resolve_account_id
# ---------------------------------------------------------------------------


def test_resolve_account_id_returns_first_account() -> None:
    client = MagicMock()
    client.get_first_account_id.return_value = "acct-1"
    result = _resolve_account_id(client)
    assert result == "acct-1"


def test_resolve_account_id_returns_none_when_no_account() -> None:
    client = MagicMock()
    client.get_first_account_id.return_value = None
    result = _resolve_account_id(client)
    assert result is None


def test_resolve_account_id_returns_none_on_auth_error() -> None:
    client = MagicMock()
    client.get_first_account_id.side_effect = CloudflareAuthError("403")
    result = _resolve_account_id(client)
    assert result is None


def test_resolve_account_id_returns_none_on_api_error() -> None:
    client = MagicMock()
    client.get_first_account_id.side_effect = CloudflareAPIError("500 server error")
    result = _resolve_account_id(client)
    assert result is None


# ---------------------------------------------------------------------------
# Error message truncation
# ---------------------------------------------------------------------------


def test_long_error_message_is_truncated() -> None:
    long_msg = "x" * 500
    client = _make_client(probe_side_effects={"get_zone": CloudflareAPIError(long_msg)})
    results = validate_token_permissions(
        client,
        zone_id="zone-abc",
        permissions=[ZONE_READ],
        probe_delay_seconds=0,
    )
    # Unrecognized error (no "403" or "404") -> STATUS_ERROR with truncated message
    assert len(results[0].message) <= 120


# ---------------------------------------------------------------------------
# Unregistered / unknown permission
# ---------------------------------------------------------------------------


def test_unregistered_permission_yields_skipped_status() -> None:
    client = _make_client()
    results = validate_token_permissions(
        client,
        zone_id="zone-abc",
        permissions=["Zone > Something Unknown"],
        probe_delay_seconds=0,
    )
    assert results[0].status == STATUS_SKIPPED
    assert "Not required by any enabled module" in results[0].message


# ---------------------------------------------------------------------------
# used_by field populated from registry
# ---------------------------------------------------------------------------


def test_used_by_populated_for_zone_read() -> None:
    """ZONE_READ should be used by multiple streams."""
    client = _make_client()
    results = validate_token_permissions(
        client,
        zone_id="zone-abc",
        permissions=[ZONE_READ],
        probe_delay_seconds=0,
    )
    # dns, http, cache, security, http_adaptive + zone_health all need ZONE_READ
    assert len(results[0].used_by) > 1


def test_used_by_populated_for_audit_permission() -> None:
    """ACCOUNT_AUDIT_READ should be used by the audit stream."""
    client = _make_client()
    results = validate_token_permissions(
        client,
        zone_id="zone-abc",
        permissions=[ACCOUNT_AUDIT_READ],
        probe_delay_seconds=0,
    )
    assert "audit" in results[0].used_by


def test_used_by_empty_for_unknown_permission() -> None:
    client = _make_client()
    results = validate_token_permissions(
        client,
        zone_id="zone-abc",
        permissions=["Zone > Something Unknown"],
        probe_delay_seconds=0,
    )
    assert results[0].used_by == ()


def test_zone_health_in_used_by_for_settings_permission() -> None:
    """ZONE_SETTINGS_READ should list zone_health as a consumer."""
    client = _make_client()
    results = validate_token_permissions(
        client,
        zone_id="zone-abc",
        permissions=[ZONE_SETTINGS_READ],
        probe_delay_seconds=0,
    )
    assert "zone_health" in results[0].used_by


# ---------------------------------------------------------------------------
# validate_token_permissions - enabled_streams filtering
# ---------------------------------------------------------------------------


def test_permission_skipped_when_not_in_enabled_streams() -> None:
    client = _make_client()
    # ACCOUNT_AUDIT_READ is used by 'audit'.
    # If we only enable 'dns', it should be skipped.
    results = validate_token_permissions(
        client,
        zone_id="zone-abc",
        permissions=[ACCOUNT_AUDIT_READ],
        enabled_streams=["dns"],
        probe_delay_seconds=0,
    )
    assert results[0].status == STATUS_SKIPPED
    assert "Not required by any enabled module" in results[0].message


def test_permission_probed_when_in_enabled_streams() -> None:
    client = _make_client()
    # ACCOUNT_AUDIT_READ is used by 'audit'.
    # If we enable 'audit', it should be probed.
    results = validate_token_permissions(
        client,
        zone_id="zone-abc",
        permissions=[ACCOUNT_AUDIT_READ],
        enabled_streams=["audit"],
        probe_delay_seconds=0,
    )
    assert results[0].status == STATUS_OK


def test_zone_health_permissions_always_probed() -> None:
    client = _make_client()
    # ZONE_SETTINGS_READ is used by 'zone_health'.
    # It should be probed even if enabled_streams doesn't include it.
    results = validate_token_permissions(
        client,
        zone_id="zone-abc",
        permissions=[ZONE_SETTINGS_READ],
        enabled_streams=["dns"],
        probe_delay_seconds=0,
    )
    assert results[0].status == STATUS_OK


# ---------------------------------------------------------------------------
# validate_token_permissions - write detection
# ---------------------------------------------------------------------------


def test_write_access_not_detected_on_403() -> None:
    """If the write probe returns 403, write access is NOT detected (good)."""
    client = _make_client(
        probe_side_effects={"sdk.dns.records.create": CloudflareAuthError("403 Forbidden")}
    )
    # We must have ZONE_READ OK for the write probe to even run
    report = validate_token_permissions(
        client,
        zone_id="zone-abc",
        permissions=[ZONE_READ],
        probe_delay_seconds=0,
    )
    assert report.write_access_detected is False


def test_write_access_detected_on_400() -> None:
    """If the write probe returns 400, write access IS detected (bad)."""
    # Create a mock exception with status_code=400 on the response
    mock_resp = MagicMock()
    mock_resp.status_code = 400
    exc = APIStatusError("Bad Request", response=mock_resp, body={})

    client = _make_client(probe_side_effects={"sdk.dns.records.create": exc})

    report = validate_token_permissions(
        client,
        zone_id="zone-abc",
        permissions=[ZONE_READ],
        probe_delay_seconds=0,
    )
    assert report.write_access_detected is True


def test_write_access_detected_on_success() -> None:
    """If the write probe somehow succeeds, write access IS detected."""
    client = _make_client()
    client.sdk.dns.records.create.return_value = {"id": "new-rec"}
    report = validate_token_permissions(
        client,
        zone_id="zone-abc",
        permissions=[ZONE_READ],
        probe_delay_seconds=0,
    )
    assert report.write_access_detected is True
