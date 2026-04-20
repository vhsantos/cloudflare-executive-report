"""Logging helpers shared by CLI entry points.

This module centralizes run-level logging setup and debug-state detection used
by sync/report commands and HTTP client verbosity toggles.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# Custom TRACE level lower than DEBUG
TRACE = 5
logging.addLevelName(TRACE, "TRACE")


def setup_logging(
    *,
    verbose_count: int = 0,
    quiet: bool = False,
    log_level: str = "warning",
    log_file: Path | None = None,
) -> None:
    """
    Configure process logging from CLI/config inputs.

    Precedence: --quiet > -v/vv/vvv > configured log_level.
    """
    if quiet:
        level = logging.ERROR
    elif verbose_count >= 3:
        level = TRACE
    elif verbose_count == 2:
        level = logging.DEBUG
    elif verbose_count == 1:
        level = logging.INFO
    else:
        raw = (log_level or "warning").strip().upper()
        level = getattr(logging, raw, logging.WARNING)

    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stderr)]
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))

    logging.basicConfig(
        level=level,
        format="%(levelname)s %(message)s",
        handlers=handlers,
        force=True,
    )

    # Suppress noisy external libraries
    logging.getLogger("svglib").setLevel(logging.ERROR)
    logging.getLogger("reportlab").setLevel(logging.ERROR)

    # HTTP trace only at TRACE level
    httpx_level = TRACE if level <= TRACE else logging.WARNING
    logging.getLogger("httpx").setLevel(httpx_level)
    logging.getLogger("httpcore").setLevel(httpx_level)

    # Suppress matplotlib font search noise
    font_level = TRACE if level <= TRACE else logging.WARNING
    logging.getLogger("findfont").setLevel(font_level)
    logging.getLogger("matplotlib").setLevel(font_level)

    # Suppress PIL/Pillow noise
    pil_level = TRACE if level <= TRACE else logging.WARNING
    logging.getLogger("PIL").setLevel(pil_level)


def effective_debug_enabled() -> bool:
    """Return True when effective root logging level is DEBUG or lower."""
    return logging.getLogger().getEffectiveLevel() <= logging.DEBUG
