"""Human-readable labels for security PDF tables (GraphQL enums vs dashboard wording)."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

_SECURITY_ACTION_LABELS: dict[str, str] = {
    "managed_challenge": "Managed Challenge",
    "js_challenge": "JS Challenge",
    "challenge": "Challenge",
    "block": "Block",
    "log": "Log",
    "allow": "Allow",
    "skip": "Skip",
    "bypass": "Bypass",
}

# Keys normalized with ``_security_source_map_key`` (lower + strip ``-`` / ``_``).
_SECURITY_SOURCE_LABELS: dict[str, str] = {
    "botfight": "Bot fight mode",
    "firewallmanaged": "Managed rules",
    "managedrules": "Managed rules",
    "bic": "Browser Integrity Check",
    "hot": "Hotlink Protection",
    "waf": "WAF",
    "ailabyrinth": "AI Labyrinth",
    "labyrinth": "AI Labyrinth",
    "ratelimit": "Rate Limiting",
    "apishield": "API Shield",
}

_CACHE_STATUS_LABELS: dict[str, str] = {
    "none": "None",
    "hit": "Hit",
    "miss": "Miss",
    "dynamic": "Dynamic",
    "revalidated": "Revalidated",
    "expired": "Expired",
    "bypass": "Bypass",
    "stale": "Stale",
    "ignored": "Ignored",
    "stream": "Stream",
    "updating": "Updating",
    "deferred": "Deferred",
}


def _security_source_map_key(raw: str) -> str:
    return raw.strip().lower().replace("-", "").replace("_", "")


def _spaced_camel(raw: str) -> str:
    s = raw.strip()
    if not s:
        return ""
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", s)
    parts = spaced.replace("_", " ").split()
    out: list[str] = []
    for p in parts:
        if p.isupper() and len(p) <= 4:
            out.append(p)
        else:
            out.append(p[:1].upper() + p[1:].lower() if p else "")
    return " ".join(out)


def format_security_action_label(raw: str) -> str:
    k = raw.strip().lower()
    if k.startswith("link_maze_"):
        return "AI Labyrinth Served"
    if k in _SECURITY_ACTION_LABELS:
        return _SECURITY_ACTION_LABELS[k]
    if not raw.strip():
        return raw
    if "_" in raw or any(c.isupper() for c in raw[1:]):
        return _spaced_camel(raw)
    return raw.strip().title()


def format_security_source_label(raw: str) -> str:
    if not raw.strip():
        return raw
    key = _security_source_map_key(raw)
    if key in _SECURITY_SOURCE_LABELS:
        return _SECURITY_SOURCE_LABELS[key]
    if "_" in raw or any(c.isupper() for c in raw[1:]):
        return _spaced_camel(raw)
    return raw.strip().title()


def format_cache_status_label(raw: str) -> str:
    k = raw.strip().lower()
    if k in _CACHE_STATUS_LABELS:
        return _CACHE_STATUS_LABELS[k]
    if not raw.strip():
        return raw
    return raw.replace("_", " ").strip().title()


def format_cache_content_type_label(raw: str) -> str:
    """Adaptive cache uses numeric content-type IDs; 1d map uses names like ``html``."""
    s = str(raw).strip()
    if not s:
        return raw
    if s.isdigit():
        return f"Type ID {s}"
    return s


def apply_row_label_formatter(
    items: list[dict[str, Any]],
    top: int,
    name_key: str,
    formatter: Callable[[str], str],
) -> list[dict[str, Any]]:
    """Copy items (up to ``top``) and replace ``name_key`` with a display string."""
    out: list[dict[str, Any]] = []
    for it in items[:top]:
        if not isinstance(it, dict):
            continue
        row = dict(it)
        row[name_key] = formatter(str(row.get(name_key) or ""))
        out.append(row)
    return out
