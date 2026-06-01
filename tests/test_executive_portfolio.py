from cloudflare_executive_report.executive.portfolio import build_portfolio_summary


def _zone(
    *,
    zone_name: str,
    score: float,
    grade: str,
    risks: list[dict],
) -> dict:
    return {
        "zone_name": zone_name,
        "executive_summary": {
            "security_score": score,
            "security_grade": grade,
            "takeaways_categorized": {"risks": risks},
        },
    }


def test_build_portfolio_summary_sorts_by_score_and_aggregates_risks() -> None:
    zones = [
        _zone(
            zone_name="b.example",
            score=70.1,
            grade="B",
            risks=[
                {"phrase_key": "dnssec", "severity": "warning"},
                {"phrase_key": "waf", "severity": "critical"},
            ],
        ),
        _zone(
            zone_name="a.example",
            score=92.3,
            grade="A",
            risks=[
                {"phrase_key": "dnssec", "severity": "warning"},
            ],
        ),
    ]

    out = build_portfolio_summary(zones, sort_by="score")
    assert out.zones_sort_caption.startswith("score asc")
    assert [row.zone_name for row in out.zones] == ["b.example", "a.example"]
    assert out.zones[0].critical_risks == 1
    assert out.zones[1].critical_risks == 0
    assert out.grade_distribution["A"] == 1
    assert out.grade_distribution["B"] == 1
    assert out.common_risks[0].phrase_key == "dnssec"
    assert out.common_risks[0].zone_count == 2


def test_build_portfolio_summary_sorts_by_zone_name() -> None:
    zones = [
        _zone(zone_name="z.example", score=10.0, grade="F", risks=[]),
        _zone(zone_name="a.example", score=90.0, grade="A", risks=[]),
    ]
    out = build_portfolio_summary(zones, sort_by="zone_name")
    assert out.zones_sort_caption.startswith("zone name")
    assert [row.zone_name for row in out.zones] == ["a.example", "z.example"]


def test_build_portfolio_summary_formats_placeholders() -> None:
    zones = [
        _zone(
            zone_name="a.example",
            score=70.0,
            grade="C+",
            risks=[
                {"phrase_key": "cert_expire_30", "severity": "warning"},
                {"phrase_key": "min_tls_version", "severity": "warning"},
            ],
        ),
    ]
    out = build_portfolio_summary(zones, sort_by="zone_name")
    risk_texts = {row.phrase_key: row.phrase_text for row in out.common_risks}
    # Check that {days} and {version} are formatted to <30 and <1.2 respectively
    assert risk_texts["cert_expire_30"] == "Certificate expires in <30 days - schedule renewal"
    assert (
        risk_texts["min_tls_version"]
        == "Minimum TLS version is <1.2 at edge - raise to at least 1.2 immediately."
    )
