from cloudflare_executive_report.aggregate import (
    build_dns_section,
    build_http_section,
    build_report,
    build_security_section,
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
    assert h["cached_requests"] == 10
    assert h["uncached_requests"] == 90
    assert h["cache_hit_ratio"] == 10.0
    assert h["encrypted_requests"] == 50
    assert h["encrypted_requests_human"] == "50"
    assert h["cached_bandwidth_bytes"] == 100
    assert h["uncached_bandwidth_bytes"] == 900
    assert h["max_uniques_single_day"] == 30
    assert h["max_uniques_single_day_human"] == "30"
    assert len(h["top_countries"]) == 2
    assert h["top_countries"][0]["code"] == "US"


def test_build_http_section_max_uniques_across_days():
    days = [
        {
            "requests": 10,
            "bytes": 100,
            "cached_requests": 1,
            "cached_bytes": 10,
            "encrypted_requests": 5,
            "page_views": 2,
            "uniques": 100,
            "country_map": [],
        },
        {
            "requests": 10,
            "bytes": 100,
            "cached_requests": 1,
            "cached_bytes": 10,
            "encrypted_requests": 5,
            "page_views": 2,
            "uniques": 250,
            "country_map": [],
        },
    ]
    h = build_http_section(days, top=1)
    assert h["unique_visitors"] == 350
    assert h["max_uniques_single_day"] == 250
    assert h["max_uniques_single_day_human"] == "250"


def test_format_helpers():
    assert format_bytes_human(0) == "0B"
    assert format_bytes_human(1024) == "1.0KB"
    assert format_bytes_human(1024 * 1024 * 3) == "3.0MB"
    assert format_count_human(1500) == "1.5K"


def test_build_security_section_empty_days():
    sec = build_security_section([], top=10)
    assert sec["total_events"] == 0
    assert sec["top_actions"] == []
    assert sec["timeseries_daily"] == []
    assert sec["top_attack_sources"] == []
    assert sec["top_source_countries"] == []
    assert sec["cache_status_breakdown"] == []
    assert sec["http_methods_breakdown"] == []
    assert sec["top_attack_paths"] == []
    assert sec["top_security_services"] == []
    assert "http_requests_sampled" not in sec
    assert "actions_among_mitigated" not in sec


def test_build_security_section_by_action():
    days = [
        {
            "by_action": [
                {"value": "block", "count": 10},
                {"value": "managed_challenge", "count": 5},
            ],
        },
        {
            "by_action": [
                {"value": "block", "count": 2},
                {"value": "log", "count": 3},
            ],
        },
    ]
    sec = build_security_section(days, top=10)
    assert sec["total_events"] == 20
    assert sec["top_actions"][0]["action"] == "block"
    assert sec["top_actions"][0]["count"] == 12
    assert sec["timeseries_daily"] == []


def test_build_security_section_coalesces_http_sampled_from_matrix_totals():
    """If daily ``http_requests_sampled`` is missing, total is mitigated + served parts."""
    days = [
        {
            "date": "2026-04-01",
            "by_action": [{"value": "block", "count": 1}],
            "mitigated_count": 100,
            "served_cf_count": 0,
            "served_origin_count": 0,
        },
    ]
    sec = build_security_section(days, top=5)
    assert sec["http_requests_sampled"] == 100
    assert sec["mitigation_rate_pct"] == 100.0


def test_build_security_section_http_enrichment_merges():
    days = [
        {
            "date": "2026-04-01",
            "by_action": [{"value": "managed_challenge", "count": 5}],
            "http_requests_sampled": 1000,
            "mitigated_count": 50,
            "served_cf_count": 200,
            "served_origin_count": 750,
            "http_by_cache_status": [{"value": "hit", "count": 200}],
            "by_http_method": [{"value": "GET", "count": 900}],
        },
        {
            "date": "2026-04-02",
            "by_action": [{"value": "block", "count": 2}],
            "http_requests_sampled": 1000,
            "mitigated_count": 10,
            "served_cf_count": 100,
            "served_origin_count": 890,
        },
    ]
    sec = build_security_section(days, top=5)
    assert sec["http_requests_sampled"] == 2000
    assert sec["mitigated_count"] == 60
    assert sec["mitigation_rate_pct"] == 3.0
    assert len(sec["timeseries_daily"]) == 2
    assert sec["actions_among_mitigated"][0]["action"] == "managed_challenge"


def test_build_security_section_merges_attack_buckets_across_days():
    days = [
        {
            "date": "2026-04-01",
            "by_action": [{"value": "block", "count": 3}],
            "by_attack_country": [{"value": "US", "count": 2}, {"value": "DE", "count": 1}],
            "attack_source_buckets": [
                {"ip": "10.0.0.1", "country": "US", "count": 2},
                {"ip": "10.0.0.2", "country": "DE", "count": 1},
            ],
        },
        {
            "date": "2026-04-02",
            "by_action": [{"value": "block", "count": 5}],
            "by_attack_country": [{"value": "US", "count": 4}, {"value": "DE", "count": 1}],
            "attack_source_buckets": [
                {"ip": "10.0.0.1", "country": "US", "count": 3},
            ],
        },
    ]
    sec = build_security_section(days, top=10)
    assert sec["total_events"] == 8
    tops = {r["ip"]: r["count"] for r in sec["top_attack_sources"]}
    assert tops["10.0.0.1"] == 5
    assert tops["10.0.0.2"] == 1
    cc = {r["code"]: r["requests"] for r in sec["top_source_countries"]}
    assert cc["US"] == 6
    assert cc["DE"] == 2


def test_fetcher_registry_matches_section_builders():
    from cloudflare_executive_report.aggregate import SECTION_BUILDERS
    from cloudflare_executive_report.fetchers.registry import FETCHER_REGISTRY

    assert set(FETCHER_REGISTRY.keys()) == set(SECTION_BUILDERS.keys())
