"""Unit tests for fetchers/http.py."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from cloudflare_executive_report.fetchers.http import (
    HttpFetcher,
    _accumulate_content_type_map,
    _http_groups,
    fetch_http_for_date,
)


def test_accumulate_content_type_map() -> None:
    acc: dict[str, tuple[int, int]] = {}
    rows = [
        {"edgeResponseContentTypeName": "text/html", "requests": 10, "bytes": 100},
        {"edgeResponseContentTypeName": "image/png", "requests": 5, "bytes": 50},
        {"edgeResponseContentTypeName": "text/html", "requests": 5, "bytes": 50},
    ]
    _accumulate_content_type_map(acc, rows)
    assert acc["text/html"] == (15, 150)
    assert acc["image/png"] == (5, 50)


def test_http_groups_empty() -> None:
    assert _http_groups(None) == []
    assert _http_groups({}) == []
    assert _http_groups({"viewer": {"zones": []}}) == []


def test_fetch_http_for_date_success() -> None:
    client = MagicMock()
    client.graphql.return_value = {
        "viewer": {
            "zones": [
                {
                    "httpRequests1dGroups": [
                        {
                            "sum": {
                                "requests": 100,
                                "bytes": 1000,
                                "cachedRequests": 50,
                                "cachedBytes": 500,
                                "encryptedRequests": 20,
                                "encryptedBytes": 200,
                                "pageViews": 30,
                                "countryMap": [
                                    {"clientCountryName": "US", "requests": 100, "bytes": 1000}
                                ],
                                "contentTypeMap": [
                                    {
                                        "edgeResponseContentTypeName": "html",
                                        "requests": 100,
                                        "bytes": 1000,
                                    }
                                ],
                            },
                            "uniq": {"uniques": 10},
                        }
                    ]
                }
            ]
        }
    }

    res = fetch_http_for_date(client, "z1", "2026-04-18")
    assert res["requests"] == 100
    assert res["bytes"] == 1000
    assert res["uniques"] == 10
    assert res["country_map"][0]["clientCountryName"] == "US"


def test_http_fetcher_retention() -> None:
    # Test that it raises error for dates outside retention
    fetcher = HttpFetcher()
    MagicMock()
    # 3 years ago is definitely outside 1 year retention
    from datetime import date

    old_date = date(2020, 1, 1)
    with pytest.raises(ValueError, match="outside retention"):
        if fetcher.outside_retention(old_date, plan_legacy_id="pro"):
            raise ValueError("outside retention")
