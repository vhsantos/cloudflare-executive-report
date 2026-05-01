"""Optional AI-generated executive summary (requires the 'ai' extra)."""

from cloudflare_executive_report.ai.formatter import format_portfolio_as_text, print_ai_summary
from cloudflare_executive_report.ai.summary import generate_ai_summary

__all__ = [
    "format_portfolio_as_text",
    "generate_ai_summary",
    "print_ai_summary",
]
