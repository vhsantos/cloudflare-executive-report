"""AI-generated executive summary orchestration."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from cloudflare_executive_report.ai.client import call_llm
from cloudflare_executive_report.ai.formatter import format_portfolio_as_text
from cloudflare_executive_report.ai.prompts import SYSTEM_PROMPT, USER_PROMPT
from cloudflare_executive_report.common.constants import CLI_SEP_HEAVY, CLI_SEP_LIGHT

if TYPE_CHECKING:
    from cloudflare_executive_report.config import AiSummaryConfig
    from cloudflare_executive_report.executive.portfolio import PortfolioSummary

log = logging.getLogger(__name__)

_MIN_PORTFOLIO_TEXT_LEN = 50


def generate_ai_summary(
    portfolio: PortfolioSummary,
    cfg: AiSummaryConfig,
) -> str | None:
    """Generate a plain-text executive summary from a PortfolioSummary.

    Tries the primary model then each configured fallback in order.
    Returns None on any failure - the report always completes regardless.

    Args:
        portfolio: Multi-zone portfolio computed by ``build_portfolio_summary``.
        cfg: AI summary configuration (subset of AppConfig).

    Returns:
        Generated summary string, or ``None`` if generation failed or is
        disabled in config.
    """
    if not cfg.enabled:
        return None

    portfolio_text = format_portfolio_as_text(portfolio)
    if len(portfolio_text.strip()) < _MIN_PORTFOLIO_TEXT_LEN:
        log.warning(
            "Portfolio text is too short (%d chars) to generate a useful AI summary — skipping.",
            len(portfolio_text.strip()),
        )
        return None

    messages: list[dict[str, str]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": USER_PROMPT.format(multi_zone_summary=portfolio_text)},
    ]

    # Build the full message once for logging/debugging
    prompt_display = (
        f"Sending to AI model (system prompt + user prompt):\n"
        f"{CLI_SEP_HEAVY}\n"
        f"SYSTEM PROMPT:\n{SYSTEM_PROMPT}\n"
        f"{CLI_SEP_LIGHT}\n"
        f"USER PROMPT:\n{USER_PROMPT.format(multi_zone_summary=portfolio_text)}\n"
        f"{CLI_SEP_HEAVY}"
    )
    log.info(prompt_display)

    # Use API Key from environment variable
    api_key = cfg.api_key.strip() or None

    # Get the list of models (default + fallbacks) to try
    models = [m for m in [cfg.model, *cfg.fallback_models] if m and m.strip()]

    if not models:
        log.error("No AI models configured - skipping summary generation.")
        return None

    for attempt_index, model in enumerate(models):
        if attempt_index > 0:
            time.sleep(2)

        log.info(
            "Attempting AI summary with model %d/%d: %s", attempt_index + 1, len(models), model
        )
        result = call_llm(
            messages,
            model=model,
            max_tokens=cfg.max_tokens,
            temperature=cfg.temperature,
            timeout=cfg.timeout_seconds,
            api_key=api_key,
        )
        if result:
            log.info("AI summary generated successfully using model: %s", model)
            return result

    log.error("All %d AI model(s) failed to generate summary.", len(models))
    return None
