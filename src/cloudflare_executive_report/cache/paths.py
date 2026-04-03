"""Filesystem paths for zone index (per-day paths come from fetcher registry)."""

from __future__ import annotations

from pathlib import Path


def index_path(cache_root: Path, zone_id: str) -> Path:
    return cache_root / zone_id / "_index.json"
