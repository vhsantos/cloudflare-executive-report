"""Registered cache fetchers by stream."""

from __future__ import annotations

from cloudflare_executive_report.cache.paths import CacheStream
from cloudflare_executive_report.fetchers.dns import DnsFetcher
from cloudflare_executive_report.fetchers.http import HttpFetcher
from cloudflare_executive_report.fetchers.security import SecurityFetcher
from cloudflare_executive_report.fetchers.types import Fetcher

FETCHER_REGISTRY: dict[CacheStream, Fetcher] = {
    CacheStream.dns: DnsFetcher(),
    CacheStream.http: HttpFetcher(),
    CacheStream.security: SecurityFetcher(),
}
