"""Logging: config ``log_level`` and CLI ``--verbose`` / ``--quiet``."""

from __future__ import annotations

import logging
import sys


def setup_logging(*, verbose: bool, quiet: bool, log_level: str = "info") -> None:
    """
    Resolve one effective level: ``--quiet`` > ``--verbose`` > ``log_level`` (config).

    ``--verbose`` is equivalent to ``log_level: debug`` for that run (overrides config).
    """
    if quiet and verbose:
        verbose = False
    if quiet:
        level = logging.ERROR
    elif verbose:
        level = logging.DEBUG
    else:
        raw = (log_level or "info").strip().upper()
        level = getattr(logging, raw, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(levelname)s %(message)s",
        stream=sys.stderr,
        force=True,
    )
    # httpx/httpcore: noisy unless we're in full debug (config or -v).
    deep = effective_debug_enabled()
    httpx_level = logging.DEBUG if deep else logging.WARNING
    logging.getLogger("httpx").setLevel(httpx_level)
    logging.getLogger("httpcore").setLevel(httpx_level)


def effective_debug_enabled() -> bool:
    """True when root logging is DEBUG (after ``setup_logging``)."""
    return logging.getLogger().getEffectiveLevel() <= logging.DEBUG
