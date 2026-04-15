"""Cloudflare Executive Report CLI - multi-zone reporting, cache, and JSON output."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("cloudflare-executive-report")
except PackageNotFoundError:
    __version__ = "0.0.0"
