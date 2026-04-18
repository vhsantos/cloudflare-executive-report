"""Registered fetchers: single place to add a new dataset."""

from __future__ import annotations

import re
from pathlib import Path

from cloudflare_executive_report.fetchers.audit import AuditFetcher
from cloudflare_executive_report.fetchers.cache import CacheFetcher
from cloudflare_executive_report.fetchers.certificates import CertificatesFetcher
from cloudflare_executive_report.fetchers.dns import DnsFetcher
from cloudflare_executive_report.fetchers.dns_records import DnsRecordsFetcher
from cloudflare_executive_report.fetchers.http import HttpFetcher
from cloudflare_executive_report.fetchers.http_adaptive import HttpAdaptiveFetcher
from cloudflare_executive_report.fetchers.security import SecurityFetcher
from cloudflare_executive_report.fetchers.types import Fetcher

# Insertion order is used everywhere (sync, CLI, PDF): PDF sections are the first four ids;
# remaining streams follow (no PDF page for those).
FETCHER_REGISTRY: dict[str, Fetcher] = {
    "dns": DnsFetcher(),
    "http": HttpFetcher(),
    "cache": CacheFetcher(),
    "security": SecurityFetcher(),
    "http_adaptive": HttpAdaptiveFetcher(),
    "dns_records": DnsRecordsFetcher(),
    "audit": AuditFetcher(),
    "certificates": CertificatesFetcher(),
}


def _validate_registry() -> None:
    for sid, fetcher in FETCHER_REGISTRY.items():
        # Ensure required ClassVar attributes are present at runtime
        for attr in ("stream_id", "cache_filename", "collect_label"):
            if not hasattr(fetcher, attr) or not getattr(fetcher, attr):
                raise TypeError(f"Fetcher {fetcher.__class__.__name__} missing ClassVar: {attr}")
        if fetcher.stream_id != sid:
            raise ValueError(f"Fetcher registry ID mismatch: {sid} != {fetcher.stream_id}")


_validate_registry()


def registered_stream_ids() -> tuple[str, ...]:
    return tuple(FETCHER_REGISTRY.keys())


def default_types_csv() -> str:
    return ",".join(FETCHER_REGISTRY.keys())


def day_cache_path(cache_root: Path, zone_id: str, day_yyyy_mm_dd: str, stream_id: str) -> Path:
    # Basic path traversal validation for zone_id
    if not re.fullmatch(r"^[a-zA-Z0-9]+$", zone_id):
        raise ValueError(f"Potential path traversal in zone_id: {zone_id}")

    fn = FETCHER_REGISTRY[stream_id].cache_filename
    return cache_root / zone_id / day_yyyy_mm_dd / fn
