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
                {"phrase_key": "review_dnssec", "severity": "warning"},
                {"phrase_key": "waf_off", "severity": "critical"},
            ],
        ),
        _zone(
            zone_name="a.example",
            score=92.3,
            grade="A",
            risks=[
                {"phrase_key": "review_dnssec", "severity": "warning"},
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
    assert out.common_risks[0].phrase_key == "review_dnssec"
    assert out.common_risks[0].zone_count == 2


def test_build_portfolio_summary_sorts_by_zone_name() -> None:
    zones = [
        _zone(zone_name="z.example", score=10.0, grade="F", risks=[]),
        _zone(zone_name="a.example", score=90.0, grade="A", risks=[]),
    ]
    out = build_portfolio_summary(zones, sort_by="zone_name")
    assert out.zones_sort_caption.startswith("zone name")
    assert [row.zone_name for row in out.zones] == ["a.example", "z.example"]
