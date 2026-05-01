"""litellm wrapper for AI summary generation.

litellm is an optional dependency - import failures are handled gracefully.
All failures return None rather than raising, so the report always completes.
"""

from __future__ import annotations

import logging
import types
from typing import Any, cast

from cloudflare_executive_report.common.logging_config import TRACE

log = logging.getLogger(__name__)

# Module-level state: None = not yet checked, False = unavailable, module = available.
_LITELLM_MODULE: types.ModuleType | None | bool = None
_LITELLM_EXCEPTIONS: dict[str, type | None] = {}


def _get_litellm() -> types.ModuleType | None:
    """Return the litellm module if available, caching the result."""
    global _LITELLM_MODULE, _LITELLM_EXCEPTIONS
    if _LITELLM_MODULE is False:
        return None
    if _LITELLM_MODULE is not None:
        return _LITELLM_MODULE  # type: ignore[return-value]
    try:
        import litellm

        _LITELLM_EXCEPTIONS = {
            "RateLimitError": getattr(litellm, "RateLimitError", None),
            "Timeout": getattr(litellm, "Timeout", None),
            "APIError": getattr(litellm, "APIError", None),
            "AuthenticationError": getattr(litellm, "AuthenticationError", None),
        }

        _LITELLM_MODULE = litellm
        return _LITELLM_MODULE  # This is definitely a ModuleType
    except ImportError:
        _LITELLM_MODULE = False
        log.warning(
            "litellm not installed - AI summary unavailable. "
            "Install with: pip install 'cloudflare-executive-report[ai]'"
        )
        return None


def _extract_content(response: Any) -> str | None:
    """Extract text content from various response formats.

    Handles:
    - Standard models: content field
    - Reasoning models: may have content in reasoning_content field
    - Models that hit token limits: returns None with warning
    """
    try:
        choices = response.choices
        if not choices:
            log.warning("Response has no choices")
            return None

        message = choices[0].message

        # Try standard content field first
        if hasattr(message, "content") and message.content:
            content = str(message.content).strip()
            if content:
                return content

        # Try reasoning_content (some reasoning models put final answer here)
        if hasattr(message, "reasoning_content") and message.reasoning_content:
            content = str(message.reasoning_content).strip()
            if content:
                log.debug("Extracted content from reasoning_content field")
                return content

        # Check finish_reason for troubleshooting
        finish_reason = getattr(choices[0], "finish_reason", None)
        if finish_reason == "length":
            log.warning(
                "Model hit token limit (finish_reason=length). Increase max_tokens (current=%d)",
                getattr(response, "usage", {}).get("completion_tokens", "unknown"),
            )
        elif finish_reason:
            log.warning("Model finished with reason: %s but no content found", finish_reason)

        return None

    except (AttributeError, IndexError, TypeError) as exc:
        log.warning("Unexpected response structure: %s", exc)
        return None


def call_llm(
    messages: list[dict[str, str]],
    *,
    model: str,
    max_tokens: int,
    temperature: float,
    timeout: int,
    api_key: str | None = None,
) -> str | None:
    """Call litellm with the given messages and return text content.

    Args:
        messages: Chat messages in OpenAI format.
        model: litellm model string (e.g. ``openrouter/google/gemma-2-9b-it:free``).
        max_tokens: Maximum tokens in the completion.
        temperature: Sampling temperature.
        timeout: Request timeout in seconds.
        api_key: Optional API key. When provided it is passed to litellm directly,
            avoiding the need for an environment variable.

    Returns:
        The generated text, or ``None`` on any failure.
    """
    litellm = _get_litellm()
    if litellm is None:
        return None

    # Only suppress debug info if not in TRACE mode (-vvv)
    current_level = logging.getLogger().getEffectiveLevel()
    if hasattr(litellm, "suppress_debug_info"):
        litellm.suppress_debug_info = bool(current_level > TRACE)  # type: ignore[attr-defined]

    kwargs: dict[str, object] = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "timeout": timeout,
        "reasoning": {"enabled": False},
    }
    if api_key:
        kwargs["api_key"] = api_key

    # Get exception classes
    RateLimitError = cast(Any, _LITELLM_EXCEPTIONS.get("RateLimitError") or Exception)
    Timeout = cast(Any, _LITELLM_EXCEPTIONS.get("Timeout") or Exception)
    APIError = cast(Any, _LITELLM_EXCEPTIONS.get("APIError") or Exception)
    AuthenticationError = cast(Any, _LITELLM_EXCEPTIONS.get("AuthenticationError") or Exception)

    try:
        response = litellm.completion(**kwargs)
    except RateLimitError:
        log.warning('Model %s failed because "rate limited", trying next fallback', model)
        return None
    except Timeout:
        log.warning('Model %s failed because "timeout", trying next fallback', model)
        return None
    except AuthenticationError:
        log.warning('Model %s failed because "authentication error", trying next fallback', model)
        return None
    except APIError:
        log.warning('Model %s failed because "API error", trying next fallback', model)
        return None
    except Exception as exc:
        log.warning('Model %s failed because "%s", trying next fallback', model, type(exc).__name__)
        return None

    content = _extract_content(response)

    if not content or not str(content).strip():
        log.warning("Model %s returned empty content, trying next fallback", model)
        return None

    return str(content).strip()
