"""Safe type conversion helpers for API response processing."""

from __future__ import annotations

from typing import Any


def as_int(v: Any, default: int = 0) -> int:
    """Safely convert value to integer."""
    if v is None:
        return default
    try:
        return int(v)
    except (ValueError, TypeError):
        return default


def as_float(v: Any, default: float = 0.0) -> float:
    """Safely convert value to float."""
    if v is None:
        return default
    try:
        return float(v)
    except (ValueError, TypeError):
        return default


def as_dict(v: Any) -> dict[str, Any]:
    """Ensure value is a dictionary."""
    if isinstance(v, dict):
        return v
    return {}
