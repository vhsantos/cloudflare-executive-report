"""Build portfolio summary rows from per-zone executive summaries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from cloudflare_executive_report.common.safe_types import as_dict
from cloudflare_executive_report.executive.phrase_catalog import get_phrase

GRADE_ORDER: tuple[str, ...] = ("A+", "A", "B", "C+", "C", "D+", "D", "F")

# Band text for portfolio PDF; thresholds must match summary._grade_for_security_posture_score.
GRADE_BAND_LABELS: dict[str, str] = {
    "A+": "A+ (>=95)",
    "A": "A (85-94)",
    "B": "B (75-84)",
    "C+": "C+ (65-74)",
    "C": "C (55-64)",
    "D+": "D+ (45-54)",
    "D": "D (35-44)",
    "F": "F (<35)",
}


@dataclass(frozen=True)
class PortfolioZoneRow:
    """One zone row in the portfolio table."""

    zone_name: str
    security_score: float
    security_grade: str
    critical_risks: int
    warning_risks: int


@dataclass(frozen=True)
class PortfolioRiskRow:
    """One aggregated risk row across zones."""

    phrase_key: str
    phrase_text: str
    check_id: str
    zone_count: int


@dataclass(frozen=True)
class PortfolioSummary:
    """Portfolio totals and rows rendered on the multi-zone summary page."""

    zones: list[PortfolioZoneRow]
    common_risks: list[PortfolioRiskRow]
    grade_distribution: dict[str, int]
    zones_sort_caption: str


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _safe_score(raw: Any) -> float:
    try:
        return round(float(raw), 1)
    except (TypeError, ValueError):
        return 0.0


def build_portfolio_summary(
    zone_blocks: list[dict[str, Any]],
    *,
    sort_by: Literal["score", "zone_name"],
) -> PortfolioSummary:
    """Aggregate multi-zone executive summary data for portfolio PDF section."""
    zone_rows: list[PortfolioZoneRow] = []
    risk_zone_counts: dict[str, int] = {}
    grade_distribution = {grade: 0 for grade in GRADE_ORDER}

    for zone in zone_blocks:
        zone_name = str(zone.get("zone_name") or zone.get("zone_id") or "").strip()
        summary = as_dict(zone.get("executive_summary"))
        score = _safe_score(summary.get("security_score"))
        grade = str(summary.get("security_grade") or "").strip() or "F"
        if grade not in grade_distribution:
            grade_distribution[grade] = 0
        grade_distribution[grade] += 1

        risks = _as_list(as_dict(summary.get("takeaways_categorized")).get("risks"))
        critical_count = 0
        warning_count = 0
        unique_phrase_keys: set[str] = set()
        for entry in risks:
            row = as_dict(entry)
            severity = str(row.get("severity") or "").strip().lower()
            if severity == "critical":
                critical_count += 1
            elif severity == "warning":
                warning_count += 1
            phrase_key = str(row.get("phrase_key") or "").strip()
            if phrase_key:
                unique_phrase_keys.add(phrase_key)

        for phrase_key in unique_phrase_keys:
            risk_zone_counts[phrase_key] = risk_zone_counts.get(phrase_key, 0) + 1

        zone_rows.append(
            PortfolioZoneRow(
                zone_name=zone_name or "-",
                security_score=score,
                security_grade=grade,
                critical_risks=critical_count,
                warning_risks=warning_count,
            )
        )

    if sort_by == "zone_name":
        zones_sort_caption = "zone name (a-z)"
        zone_rows = sorted(zone_rows, key=lambda row: row.zone_name.lower())
    else:
        zones_sort_caption = "score asc (worst first), tie-break zone name (a-z)"
        zone_rows = sorted(zone_rows, key=lambda row: (row.security_score, row.zone_name.lower()))

    common_risks: list[PortfolioRiskRow] = []
    for phrase_key, zone_count in sorted(
        risk_zone_counts.items(),
        key=lambda item: (-item[1], item[0]),
    ):
        phrase_data = get_phrase(phrase_key, "risk")
        phrase_text = str(phrase_data["text"])
        check_id = str(phrase_data["id"])
        common_risks.append(
            PortfolioRiskRow(
                phrase_key=phrase_key,
                phrase_text=phrase_text,
                check_id=check_id,
                zone_count=zone_count,
            )
        )

    return PortfolioSummary(
        zones=zone_rows,
        common_risks=common_risks,
        grade_distribution=grade_distribution,
        zones_sort_caption=zones_sort_caption,
    )
