"""Report and per-stream layout configuration."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class DnsStreamLayout:
    blocks: tuple[str, ...] = (
        "header",
        "kpi",
        "map",
        "colo_table",
        "qnames_rtypes",
        "rcode_proto",
        "timeseries",
    )


@dataclass(frozen=True)
class HttpStreamLayout:
    blocks: tuple[str, ...] = (
        "header",
        "kpi",
        "map",
        "countries",
        "timeseries",
    )


@dataclass(frozen=True)
class SecurityStreamLayout:
    blocks: tuple[str, ...] = (
        "header",
        "kpi",
        "timeseries",
        "actions",
        "services",
        "attack_sources",
        "attack_paths",
        "countries",
        "cache",
        "methods",
    )


@dataclass(frozen=True)
class CacheStreamLayout:
    blocks: tuple[str, ...] = (
        "header",
        "kpi",
        "timeseries",
        "status",
        "paths",
        "mime_http_1d",
    )


@dataclass
class ReportSpec:
    zone_ids: list[str]
    start: str
    end: str
    streams: tuple[str, ...] = ("dns", "http")
    top: int = 10
    dns_layout: DnsStreamLayout = field(default_factory=DnsStreamLayout)
    http_layout: HttpStreamLayout = field(default_factory=HttpStreamLayout)
    security_layout: SecurityStreamLayout = field(default_factory=SecurityStreamLayout)
    cache_layout: CacheStreamLayout = field(default_factory=CacheStreamLayout)
