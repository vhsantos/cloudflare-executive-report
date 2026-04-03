from cloudflare_executive_report.aggregate import (
    build_dns_section,
    build_http_section,
    build_report,
    format_bytes_human,
    format_count_human,
)


def test_build_dns_section_merges_days():
    days = [
        {
            "total_queries": 100,
            "avg_processing_time_us": 1000.0,
            "by_query_name": [{"value": "a.example", "count": 60}],
            "by_query_type": [{"value": "A", "count": 100}],
            "by_response_code": [{"value": "NOERROR", "count": 100}],
            "by_colo": [{"value": "IAD", "count": 100}],
            "by_protocol": [{"value": "UDP", "count": 90}],
            "by_ip_version": [{"value": "4", "count": 100}],
        },
        {
            "total_queries": 100,
            "avg_processing_time_us": 3000.0,
            "by_query_name": [{"value": "a.example", "count": 40}],
            "by_query_type": [{"value": "A", "count": 100}],
            "by_response_code": [{"value": "NOERROR", "count": 100}],
            "by_colo": [{"value": "IAD", "count": 100}],
            "by_protocol": [{"value": "UDP", "count": 110}],
            "by_ip_version": [{"value": "4", "count": 100}],
        },
    ]
    dns = build_dns_section(days)
    assert dns["total_queries"] == 200
    assert dns["average_processing_time_ms"] == 2.0
    assert dns["top_query_names"][0]["count"] == 100


def test_build_report_shape():
    r = build_report(
        zones_out=[],
        warnings=[],
        period_start="2026-03-01",
        period_end="2026-03-07",
        requested_start="2026-03-01",
        requested_end="2026-03-07",
    )
    assert r["report_period"]["timezone"] == "UTC"
    assert "tool_version" in r


def test_build_http_section_top_countries():
    days = [
        {
            "requests": 100,
            "bytes": 1000,
            "cached_requests": 10,
            "cached_bytes": 100,
            "encrypted_requests": 50,
            "page_views": 20,
            "uniques": 30,
            "country_map": [
                {"clientCountryName": "US", "requests": 60, "bytes": 600},
                {"clientCountryName": "DE", "requests": 40, "bytes": 400},
            ],
        }
    ]
    h = build_http_section(days, top=2)
    assert h["total_requests"] == 100
    assert h["cache_hit_ratio"] == 10.0
    assert len(h["top_countries"]) == 2
    assert h["top_countries"][0]["code"] == "US"


def test_format_helpers():
    assert format_bytes_human(1024) == "1.0 KB"
    assert format_count_human(1500) == "1.5K"
