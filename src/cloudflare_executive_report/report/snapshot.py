"""Load and save report JSON files on disk."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from cloudflare_executive_report.common.period_resolver import compute_fingerprint_hash
from cloudflare_executive_report.common.report_snapshot import data_fingerprint_matches

if TYPE_CHECKING:
    from cloudflare_executive_report.config import AppConfig


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
    """Write report dict to path atomically (temp file + fsync + rename)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    with tmp.open("w", encoding="utf-8") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    tmp.replace(path)
    if not quiet:
        print(f"Wrote {path}", flush=True)


def find_and_extract_reusable_snapshot(
    cfg: AppConfig,
    requested_fingerprint: dict[str, Any],
    requested_zones: list[str],
) -> dict[str, Any] | None:
    """Find a snapshot that matches the fingerprint and contains all requested zones.

    If found, returns a copy of the snapshot with the `zones` array filtered to only include
    the requested zones.
    """
    if not requested_zones:
        return None

    fp_hash = compute_fingerprint_hash(requested_fingerprint)

    # Candidate files: outputs/cf_report.json and history/cf_report_{hash}_*.json
    candidates: list[Path] = []

    current_path = cfg.report_current_path()
    if current_path.is_file():
        candidates.append(current_path)

    history_dir = cfg.report_history_dir()
    if history_dir.is_dir():
        candidates.extend(history_dir.glob(f"cf_report_{fp_hash}_*.json"))

    # Sort by timestamp descending (newest first).
    # The filename includes the timestamp or we can sort by stat().st_mtime
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    req_zones_set = set(requested_zones)

    for candidate in candidates:
        snapshot = load_report_json(candidate)
        if not snapshot:
            continue

        # Double check fingerprint matches (in case hash collides or checking cf_report.json)
        if not data_fingerprint_matches(snapshot, requested_fingerprint):
            continue

        snapshot_zones = snapshot.get("zones", [])
        snapshot_zone_ids = {z.get("zone_id") for z in snapshot_zones}

        # Check if requested zones are a subset of the snapshot's zones
        if req_zones_set.issubset(snapshot_zone_ids):
            # We found a superset snapshot! Extract just the requested zones.
            extracted_zones = [z for z in snapshot_zones if z.get("zone_id") in req_zones_set]

            import logging

            log = logging.getLogger(__name__)
            log.info("Reusing existing report snapshot from %s", candidate)

            # Create a copy to avoid mutating the cached/loaded dict
            extracted = dict(snapshot)
            extracted["zones"] = extracted_zones
            return extracted

    return None
