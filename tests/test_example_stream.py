"""Tests for the example skeleton stream.

Copy this file when adding a new stream (replace ``example`` / ``Example``).
Delete the skeleton assertions and add tests that reflect your real payload.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from cloudflare_executive_report.aggregators.example import build_example_section
from cloudflare_executive_report.fetchers.example import (
    ExampleFetcher,
    fetch_example_for_bounds,
)

# ---------------------------------------------------------------------------
# Aggregator tests (pure functions - no API calls)
# ---------------------------------------------------------------------------


def test_build_example_section_empty_returns_zeros() -> None:
    """Empty input must not raise and must return zero counts."""
    out = build_example_section([])
    assert out["total_count"] == 0
    assert out["top_dimensions"] == []


def test_build_example_section_sums_across_days() -> None:
    """Counts from multiple days are summed correctly."""
    days = [
        {
            "total_count": 10,
            "by_example_dimension": [{"value": "a", "count": 10}],
        },
        {
            "total_count": 25,
            "by_example_dimension": [
                {"value": "a", "count": 15},
                {"value": "b", "count": 10},
            ],
        },
    ]
    out = build_example_section(days, top=5)
    assert out["total_count"] == 35
    assert out["top_dimensions"][0]["value"] == "a"
    assert out["top_dimensions"][0]["count"] == 25
    assert out["top_dimensions"][1]["value"] == "b"
    assert out["top_dimensions"][1]["count"] == 10


def test_build_example_section_top_limits_rows() -> None:
    """Only the top N dimensions are returned."""
    days = [
        {
            "total_count": 6,
            "by_example_dimension": [
                {"value": "a", "count": 3},
                {"value": "b", "count": 2},
                {"value": "c", "count": 1},
            ],
        }
    ]
    out = build_example_section(days, top=2)
    assert len(out["top_dimensions"]) == 2
    assert {r["value"] for r in out["top_dimensions"]} == {"a", "b"}


def test_build_example_section_percentage() -> None:
    """Percentage is computed relative to total_count."""
    days = [
        {
            "total_count": 100,
            "by_example_dimension": [
                {"value": "x", "count": 60},
                {"value": "y", "count": 40},
            ],
        }
    ]
    out = build_example_section(days, top=5)
    pcts = {r["value"]: r["percentage"] for r in out["top_dimensions"]}
    assert pcts["x"] == 60.0
    assert pcts["y"] == 40.0


def test_build_example_section_skips_malformed_rows() -> None:
    """Non-dict rows in by_example_dimension are silently skipped."""
    days = [
        {
            "total_count": 5,
            "by_example_dimension": [
                None,
                "bad",
                {"value": "ok", "count": 5},
            ],
        }
    ]
    out = build_example_section(days, top=10)
    assert out["top_dimensions"][0]["value"] == "ok"


# ---------------------------------------------------------------------------
# Fetcher unit tests (mocked client - no real API calls)
# ---------------------------------------------------------------------------


def _make_client(graphql_response: dict) -> MagicMock:
    """Return a mock CloudflareClient that always returns graphql_response."""
    client = MagicMock()
    client.graphql.return_value = graphql_response
    return client


def _example_graphql_response(rows: list[dict]) -> dict:
    """Build a minimal GraphQL response shape matching Q_EXAMPLE_DAY."""
    return {
        "viewer": {
            "zones": [
                {
                    "exg": rows,
                }
            ]
        }
    }


def test_fetch_example_for_bounds_sums_rows() -> None:
    """Rows from the GraphQL response are parsed into total_count."""
    client = _make_client(
        _example_graphql_response(
            [
                {"count": 40, "dimensions": {"exampleDimension": "alpha"}},
                {"count": 20, "dimensions": {"exampleDimension": "beta"}},
            ]
        )
    )
    result = fetch_example_for_bounds(
        client, "zone123", "2026-04-01T00:00:00Z", "2026-04-02T00:00:00Z"
    )
    assert result["total_count"] == 60
    assert result["payload_kind"] == "example_groups"
    dims = {r["value"]: r["count"] for r in result["by_example_dimension"]}
    assert dims["alpha"] == 40
    assert dims["beta"] == 20


def test_fetch_example_for_bounds_empty_zones() -> None:
    """Empty zones list must not raise."""
    client = _make_client({"viewer": {"zones": []}})
    result = fetch_example_for_bounds(
        client, "zone123", "2026-04-01T00:00:00Z", "2026-04-02T00:00:00Z"
    )
    assert result["total_count"] == 0


def test_fetch_example_for_bounds_skips_empty_dimension() -> None:
    """Rows with no dimension value are ignored."""
    client = _make_client(
        _example_graphql_response(
            [
                {"count": 10, "dimensions": {"exampleDimension": ""}},
                {"count": 5, "dimensions": {"exampleDimension": "ok"}},
            ]
        )
    )
    result = fetch_example_for_bounds(
        client, "zone123", "2026-04-01T00:00:00Z", "2026-04-02T00:00:00Z"
    )
    assert result["total_count"] == 5


# ---------------------------------------------------------------------------
# Fetcher class tests
# ---------------------------------------------------------------------------


def test_example_fetcher_class_vars() -> None:
    """ClassVar values must match the registry key and naming conventions."""
    f = ExampleFetcher()
    assert f.stream_id == "example"
    assert f.cache_filename == "example.json"
    assert f.collect_label == "Example"
    assert len(f.required_permissions) > 0


def test_example_fetcher_outside_retention_future() -> None:
    """A far-future date should not be outside retention."""
    from datetime import date

    f = ExampleFetcher()
    # Today is always within retention
    assert f.outside_retention(date.today(), plan_legacy_id=None) is False


def test_example_fetcher_append_live_today_rate_limited() -> None:
    """append_live_today must return rate_limited=True on CloudflareRateLimitError."""
    from cloudflare_executive_report.cf_client import CloudflareRateLimitError

    client = MagicMock()
    client.graphql.side_effect = CloudflareRateLimitError("rate limited")

    f = ExampleFetcher()
    payloads, warnings, rate_limited = f.append_live_today(
        client, "zone123", "example.com", plan_legacy_id=None, zone_meta=None
    )
    assert payloads == []
    assert rate_limited is True
    assert any("rate limited" in w for w in warnings)


def test_example_fetcher_append_live_today_api_error() -> None:
    """append_live_today must return rate_limited=False on generic CloudflareAPIError."""
    from cloudflare_executive_report.cf_client import CloudflareAPIError

    client = MagicMock()
    client.graphql.side_effect = CloudflareAPIError("bad request")

    f = ExampleFetcher()
    payloads, warnings, rate_limited = f.append_live_today(
        client, "zone123", "example.com", plan_legacy_id=None, zone_meta=None
    )
    assert payloads == []
    assert rate_limited is False
    assert any("example.com" in w for w in warnings)


# ---------------------------------------------------------------------------
# Registry consistency test
# ---------------------------------------------------------------------------


def test_example_not_in_registry_yet() -> None:
    """The skeleton is NOT registered by default - this test documents that.

    When you promote example -> your real stream, delete this test and add
    one that verifies your stream_id IS present in both registries.
    """
    from cloudflare_executive_report.aggregators.registry import SECTION_BUILDERS
    from cloudflare_executive_report.fetchers.registry import FETCHER_REGISTRY

    # The skeleton is intentionally absent from the live registries.
    assert "example" not in FETCHER_REGISTRY
    assert "example" not in SECTION_BUILDERS
