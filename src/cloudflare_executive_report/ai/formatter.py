"""Convert PortfolioSummary into sanitized plain text and format AI output.

All functions in this module are PII-free by design:
zone names, IP addresses, and individual zone scores are never included.
"""

from __future__ import annotations

import textwrap
from typing import TYPE_CHECKING

from cloudflare_executive_report.common.constants import CLI_SEP_HEAVY, CLI_TERMINAL_WIDTH
from cloudflare_executive_report.executive.portfolio import GRADE_BAND_LABELS

if TYPE_CHECKING:
    from cloudflare_executive_report.executive.portfolio import PortfolioSummary


def format_portfolio_as_text(portfolio: PortfolioSummary) -> str:
    """Render a sanitized plain-text block from a PortfolioSummary for AI input.

    Includes:
        - Grade distribution (counts only, no zone names).
        - Common risks (check_id + description + zone count).
        - Actions derived from common risks.

    Explicitly excludes:
        - Zone names, individual zone scores, IPs, or any PII.
    """
    lines: list[str] = ["Multi-Zone Security Summary", ""]

    # Grade distribution (counts only)
    grade_totals = {g: c for g, c in portfolio.grade_distribution.items() if c > 0}
    if grade_totals:
        lines.append("Grade distribution:")
        for grade, count in grade_totals.items():
            label = GRADE_BAND_LABELS.get(grade, grade)
            lines.append(f"  {label}: {count} zone{'s' if count != 1 else ''}")
        lines.append("")

    # Aggregate risk counts
    total_zones = sum(grade_totals.values())
    lines.append(f"Total zones evaluated: {total_zones}")

    # Common risks (check_id + description + zone count)
    if portfolio.common_risks:
        lines.append("")
        lines.append("Common risks (count of zones affected):")
        for risk in portfolio.common_risks:
            lines.append(
                f"  - {risk.phrase_text} ({risk.check_id}):"
                f" {risk.zone_count} zone{'s' if risk.zone_count != 1 else ''}"
            )
        lines.append("")
        lines.append("Actions required:")
        for risk in portfolio.common_risks:
            lines.append(f"  - [{risk.check_id}] Review and remediate: {risk.phrase_text}")

    return "\n".join(lines)


def print_ai_summary(summary: str) -> None:
    """Pretty-print an AI summary as a formatted block to stdout."""
    wrapped = textwrap.fill(summary.strip(), width=CLI_TERMINAL_WIDTH - 2, subsequent_indent="  ")
    print(f"\n{CLI_SEP_HEAVY}")
    print("AI-Generated Executive Summary".center(CLI_TERMINAL_WIDTH))
    print(CLI_SEP_HEAVY)
    print(wrapped)
    print(f"{CLI_SEP_HEAVY}\n")
