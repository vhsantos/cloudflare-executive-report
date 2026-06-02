"""Tests for CloudflareClient.list_zone_certificate_packs().

These tests patch the internal SDK object so they exercise the real method
implementation in cf_client.py - not a FakeClient bypass. This ensures SDK
changes are caught before they surface as live failures.

Requires cloudflare>=5.2 (items are Pydantic models with model_dump()).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from cloudflare_executive_report.cf_client import CloudflareAuthError, CloudflareClient


def _make_client() -> CloudflareClient:
    """Return a CloudflareClient with a mocked internal SDK and httpx."""
    with (
        patch("cloudflare_executive_report.cf_client.Cloudflare"),
        patch("cloudflare_executive_report.cf_client.httpx.Client"),
    ):
        return CloudflareClient(api_token="test-token")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_list_zone_certificate_packs_converts_pydantic_models() -> None:
    """v5 SDK returns Pydantic models - model_dump() must be called on each."""
    client = _make_client()
    mock_item1 = MagicMock()
    mock_item1.model_dump.return_value = {"id": "abc", "status": "active", "certificates": []}
    mock_item2 = MagicMock()
    mock_item2.model_dump.return_value = {
        "id": "def",
        "status": "pending_issuance",
        "certificates": [],
    }
    client._sdk.ssl.certificate_packs.list = MagicMock(return_value=iter([mock_item1, mock_item2]))

    result = client.list_zone_certificate_packs("zone-1")

    assert len(result) == 2
    assert all(isinstance(r, dict) for r in result)
    assert result[0]["status"] == "active"
    assert result[1]["status"] == "pending_issuance"
    mock_item1.model_dump.assert_called_once()
    mock_item2.model_dump.assert_called_once()


def test_list_zone_certificate_packs_empty_page() -> None:
    """Empty iterator must return an empty list."""
    client = _make_client()
    client._sdk.ssl.certificate_packs.list = MagicMock(return_value=iter([]))

    result = client.list_zone_certificate_packs("zone-1")

    assert result == []


def test_list_zone_certificate_packs_passes_zone_id_and_status() -> None:
    """SDK must always be called with zone_id and status='all'."""
    client = _make_client()
    mock_list = MagicMock(return_value=iter([]))
    client._sdk.ssl.certificate_packs.list = mock_list

    client.list_zone_certificate_packs("zone-xyz")

    mock_list.assert_called_once_with(zone_id="zone-xyz", status="all")


def test_list_zone_certificate_packs_maps_auth_exception_to_cloudflare_auth_error() -> None:
    """AuthenticationError from the SDK must be re-raised as CloudflareAuthError."""
    from cloudflare import AuthenticationError

    client = _make_client()
    mock_response = MagicMock()
    mock_response.headers = {}
    mock_response.status_code = 403
    mock_response.text = "forbidden"

    client._sdk.ssl.certificate_packs.list = MagicMock(
        side_effect=AuthenticationError(message="bad token", response=mock_response, body={})
    )

    with pytest.raises(CloudflareAuthError):
        client.list_zone_certificate_packs("zone-1")
