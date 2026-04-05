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


@dataclass
class ReportSpec:
    zone_ids: list[str]
    start: str
    end: str
    streams: tuple[str, ...] = ("dns", "http")
    top: int = 10
    dns_layout: DnsStreamLayout = field(default_factory=DnsStreamLayout)
    http_layout: HttpStreamLayout = field(default_factory=HttpStreamLayout)
