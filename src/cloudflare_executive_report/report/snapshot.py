"""Load and save report JSON files on disk."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_report_json(path: Path) -> dict[str, Any] | None:
    """Parse report JSON from path; return None on missing file or parse error."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def save_report_json(path: Path, data: dict[str, Any], *, quiet: bool = False) -> None:
    """Write report dict to path as UTF-8 JSON with trailing newline."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if not quiet:
        print(f"Wrote {path}", flush=True)
