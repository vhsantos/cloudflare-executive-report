from cloudflare_executive_report.aggregate import build_dns_section, build_report


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
