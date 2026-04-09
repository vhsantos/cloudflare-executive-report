"""Logging helpers shared by CLI entry points.

This module centralizes run-level logging setup and debug-state detection used
by sync/report commands and HTTP client verbosity toggles.
"""

from __future__ import annotations

import logging
import sys


def setup_logging(*, verbose: bool, quiet: bool, log_level: str = "info") -> None:
    """
    Configure process logging from CLI/config inputs.

    Precedence: --quiet > --verbose > configured log_level.
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
    deep = effective_debug_enabled()
    httpx_level = logging.DEBUG if deep else logging.WARNING
    logging.getLogger("httpx").setLevel(httpx_level)
    logging.getLogger("httpcore").setLevel(httpx_level)


def effective_debug_enabled() -> bool:
    """Return True when effective root logging level is DEBUG."""
    return logging.getLogger().getEffectiveLevel() <= logging.DEBUG
