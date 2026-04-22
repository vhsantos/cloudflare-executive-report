"""Boundary filtering for untrusted external data."""

from __future__ import annotations

from typing import Any


def filter_dict_rows(raw: Any) -> list[dict[str, Any]]:
    """Filter list to only dict items. Non-list or non-dict items are dropped silently.

    Use this at API and cache read boundaries to convert ``list[Any]``
    into ``list[dict[str, Any]]``. Callers downstream can then operate
    on typed data without defensive ``isinstance`` guards.

    Args:
        raw: Any value returned from an API call, SDK, or JSON load.

    Returns:
        List containing only the items that are ``dict`` instances.
        Returns an empty list for ``None``, non-list, or all-non-dict input.

    """
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]
