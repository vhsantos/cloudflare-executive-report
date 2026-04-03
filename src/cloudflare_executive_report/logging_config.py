"""Logging for --verbose / --quiet."""

from __future__ import annotations

import logging
import sys


def setup_logging(*, verbose: bool, quiet: bool, log_level: str = "info") -> None:
    if quiet and verbose:
        verbose = False
    if quiet:
        level = logging.ERROR
    elif verbose:
        level = logging.DEBUG
    else:
        level = getattr(logging, log_level.upper(), logging.INFO)
        if level < logging.INFO:
            level = logging.INFO
    logging.basicConfig(
        level=level,
        format="%(levelname)s %(message)s",
        stream=sys.stderr,
        force=True,
    )
    # httpx/httpcore log every request at INFO unless capped (noisy for normal CLI use).
    httpx_level = logging.DEBUG if verbose else logging.WARNING
    logging.getLogger("httpx").setLevel(httpx_level)
    logging.getLogger("httpcore").setLevel(httpx_level)
