"""Report date span from cache indices and sync option modes (shared by sync and report)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from cloudflare_executive_report.cache import load_zone_index
from cloudflare_executive_report.common.dates import format_ymd, last_n_complete_days, utc_today
from cloudflare_executive_report.common.period_resolver import resolved_period_for_options
from cloudflare_executive_report.fetchers.registry import registered_stream_ids
from cloudflare_executive_report.sync.options import SyncMode, SyncOptions


def streams_for_sync_types(types: frozenset[str]) -> list[str]:
    """Return registry stream ids contained in the given type set (stable order)."""
    return [sid for sid in registered_stream_ids() if sid in types]


def report_bounds_from_indices(
    zones: list,
    cache_root: Path,
    y: date,
    opts: SyncOptions,
) -> tuple[str, str]:
    """Compute inclusive report start/end strings from resolved mode or cache stream bounds."""
    resolved = resolved_period_for_options(opts=opts, y=y, today=utc_today())
    if resolved is not None:
        d0, d1 = resolved
        return format_ymd(d0), format_ymd(d1)
    if opts.mode == SyncMode.last_n and opts.last_n is not None:
        d0, d1 = last_n_complete_days(opts.last_n, yesterday=y)
        return format_ymd(d0), format_ymd(d1)
    if opts.mode == SyncMode.range and opts.start and opts.end:
        return opts.start, opts.end

    earliests: list[str] = []
    latests: list[str] = []
    for z in zones:
        ix = load_zone_index(cache_root, z.id, z.name)
        for sid in streams_for_sync_types(opts.types):
            st = ix.streams.get(sid)
            if not st:
                continue
            if st.earliest:
                earliests.append(st.earliest)
            if st.latest:
                latests.append(st.latest)
    if not earliests:
        earliests.append(format_ymd(y))
    if not latests:
        latests.append(format_ymd(y))
    return min(earliests), max(latests)
