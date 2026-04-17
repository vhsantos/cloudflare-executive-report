"""Read/write one cache envelope file (any stream)."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from cloudflare_executive_report.common.dates import utc_now_z

log = logging.getLogger(__name__)

SCHEMA_VERSION = 1


def read_json_file(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        with path.open(encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        log.warning("Corrupt cache JSON deleted: %s", path)
        try:
            path.unlink()
        except OSError:
            pass
        return None


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    data = json.dumps(payload, indent=2, ensure_ascii=False)
    with tmp.open("w", encoding="utf-8") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    tmp.replace(path)


def read_day_file(path: Path) -> dict[str, Any] | None:
    """Return full on-disk envelope dict, or None if missing/corrupt."""
    return read_json_file(path)


def write_day_file(
    path: Path,
    *,
    source: str,
    data: Any,
    error: str | None = None,
    retry_after: str | None = None,
) -> None:
    payload: dict[str, Any] = {
        "_schema_version": SCHEMA_VERSION,
        "_source": source,
        "_source_timestamp": utc_now_z(),
        "data": data,
    }
    if error:
        payload["_error"] = error
    if retry_after:
        payload["_retry_after"] = retry_after
    write_json_atomic(path, payload)
