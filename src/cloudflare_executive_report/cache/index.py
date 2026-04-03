"""Zone _index.json: earliest/latest per stream id (generic dict)."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from cloudflare_executive_report.cache.envelope import read_json_file, write_json_atomic
from cloudflare_executive_report.cache.paths import index_path


@dataclass
class IndexStream:
    earliest: str | None = None
    latest: str | None = None


@dataclass
class ZoneIndex:
    zone_id: str
    zone_name: str
    streams: dict[str, IndexStream] = field(default_factory=dict)


def _read_stream_bounds(raw: dict[str, Any], key: str) -> IndexStream:
    sec = raw.get(key) or {}
    if not isinstance(sec, dict):
        return IndexStream()
    return IndexStream(earliest=sec.get("earliest"), latest=sec.get("latest"))


def load_zone_index(cache_root: Path, zone_id: str, zone_name: str) -> ZoneIndex:
    p = index_path(cache_root, zone_id)
    raw = read_json_file(p)
    if not raw:
        return ZoneIndex(zone_id=zone_id, zone_name=zone_name)
    streams: dict[str, IndexStream] = {}
    zid = str(raw.get("zone_id") or zone_id)
    zname = str(raw.get("zone_name") or zone_name)
    for key, val in raw.items():
        if key in ("zone_id", "zone_name"):
            continue
        if isinstance(val, dict) and ("earliest" in val or "latest" in val):
            streams[key] = _read_stream_bounds(raw, key)
    return ZoneIndex(zone_id=zid, zone_name=zname, streams=streams)


def save_zone_index(cache_root: Path, idx: ZoneIndex) -> None:
    p = index_path(cache_root, idx.zone_id)

    def pack(s: IndexStream) -> dict[str, str]:
        out: dict[str, str] = {}
        if s.earliest:
            out["earliest"] = s.earliest
        if s.latest:
            out["latest"] = s.latest
        return out

    payload: dict[str, Any] = {
        "zone_id": idx.zone_id,
        "zone_name": idx.zone_name,
    }
    for sid in sorted(idx.streams):
        payload[sid] = pack(idx.streams[sid])
    write_json_atomic(p, payload)


def merge_stream_bounds(
    idx: ZoneIndex,
    start: str | None,
    end: str | None,
    stream_id: str,
) -> ZoneIndex:
    cur = idx.streams.get(stream_id, IndexStream())
    ne, nl = cur.earliest, cur.latest
    if start:
        ne = start if not ne else min(start, ne)
    if end:
        nl = end if not nl else max(end, nl)
    new_streams = dict(idx.streams)
    new_streams[stream_id] = IndexStream(earliest=ne, latest=nl)
    return replace(idx, streams=new_streams)


def update_index_after_dates(
    idx: ZoneIndex,
    dates_written: list[str],
    stream_id: str,
) -> ZoneIndex:
    if not dates_written:
        return idx
    s = min(dates_written)
    e = max(dates_written)
    return merge_stream_bounds(idx, s, e, stream_id)


def stream_latest(idx: ZoneIndex, stream_id: str) -> str | None:
    s = idx.streams.get(stream_id)
    return s.latest if s else None
