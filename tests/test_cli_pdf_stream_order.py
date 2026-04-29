"""CLI PDF stream ordering follows fetcher registry (first four PDF ids)."""

from __future__ import annotations

from cloudflare_executive_report.cli import _pdf_streams_from_types


def test_pdf_streams_order_dns_http_cache_security() -> None:
    assert _pdf_streams_from_types(frozenset({"dns", "http", "cache", "security"})) == (
        "dns",
        "http",
        "security",
        "cache",
    )


def test_pdf_streams_subset_preserves_order() -> None:
    assert _pdf_streams_from_types(frozenset({"cache", "http"})) == ("http", "cache")
    assert _pdf_streams_from_types(frozenset({"security", "dns"})) == ("dns", "security")
