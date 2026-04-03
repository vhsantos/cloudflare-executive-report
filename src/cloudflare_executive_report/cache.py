"""On-disk cache: dns.json, _index.json, .lock."""

from __future__ import annotations

import json
import logging
import os
import time
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

SCHEMA_VERSION = 1


class CacheLockTimeout(Exception):
    pass


@contextmanager
def cache_lock(cache_root: Path, wait_seconds: float = 30.0) -> Generator[None, None, None]:
    cache_root.mkdir(parents=True, exist_ok=True)
    lock_path = cache_root / ".lock"
    deadline = time.monotonic() + wait_seconds
    fd: int | None = None
    while True:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            fd = None
            break
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise CacheLockTimeout(
                    f"Cache lock still held after {wait_seconds}s: {lock_path}"
                ) from None
            time.sleep(0.25)
    try:
        yield
    finally:
        try:
            lock_path.unlink(missing_ok=True)
        except OSError:
            pass


def utc_now_z() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def dns_cache_path(cache_root: Path, zone_id: str, day: str) -> Path:
    return cache_root / zone_id / day / "dns.json"


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


@dataclass
class ZoneIndex:
    zone_id: str
    zone_name: str
    dns_earliest: str | None
    dns_latest: str | None


def index_path(cache_root: Path, zone_id: str) -> Path:
    return cache_root / zone_id / "_index.json"


def load_zone_index(cache_root: Path, zone_id: str, zone_name: str) -> ZoneIndex:
    p = index_path(cache_root, zone_id)
    raw = read_json_file(p)
    if not raw:
        return ZoneIndex(zone_id=zone_id, zone_name=zone_name, dns_earliest=None, dns_latest=None)
    dns = raw.get("dns") or {}
    return ZoneIndex(
        zone_id=str(raw.get("zone_id") or zone_id),
        zone_name=str(raw.get("zone_name") or zone_name),
        dns_earliest=dns.get("earliest"),
        dns_latest=dns.get("latest"),
    )


def save_zone_index(cache_root: Path, idx: ZoneIndex) -> None:
    p = index_path(cache_root, idx.zone_id)
    payload = {
        "zone_id": idx.zone_id,
        "zone_name": idx.zone_name,
        "dns": {},
    }
    if idx.dns_earliest:
        payload["dns"]["earliest"] = idx.dns_earliest
    if idx.dns_latest:
        payload["dns"]["latest"] = idx.dns_latest
    write_json_atomic(p, payload)


def read_dns_cache(cache_root: Path, zone_id: str, day: str) -> dict[str, Any] | None:
    return read_json_file(dns_cache_path(cache_root, zone_id, day))


def write_dns_cache(
    cache_root: Path,
    zone_id: str,
    day: str,
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
    write_json_atomic(dns_cache_path(cache_root, zone_id, day), payload)


def merge_index_bounds(
    idx: ZoneIndex,
    start: str | None,
    end: str | None,
) -> ZoneIndex:
    """Expand earliest/latest from explicit range edges (min/max with existing)."""
    ne = idx.dns_earliest
    nl = idx.dns_latest
    if start:
        ne = start if not ne else min(start, ne)
    if end:
        nl = end if not nl else max(end, nl)
    return ZoneIndex(
        zone_id=idx.zone_id,
        zone_name=idx.zone_name,
        dns_earliest=ne,
        dns_latest=nl,
    )


def update_index_after_dates(idx: ZoneIndex, dates_written: list[str]) -> ZoneIndex:
    """Bump earliest/latest to cover all dates_written (YYYY-MM-DD)."""
    if not dates_written:
        return idx
    s = min(dates_written)
    e = max(dates_written)
    out = merge_index_bounds(idx, s, e)
    return out
