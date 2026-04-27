"""Registered section builders for report aggregation."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from cloudflare_executive_report.aggregators.audit import build_audit_section
from cloudflare_executive_report.aggregators.cache import build_cache_section
from cloudflare_executive_report.aggregators.certificates import build_certificates_section
from cloudflare_executive_report.aggregators.dns import build_dns_section
from cloudflare_executive_report.aggregators.dns_records import build_dns_records_section
from cloudflare_executive_report.aggregators.email import build_email_section
from cloudflare_executive_report.aggregators.http import build_http_section
from cloudflare_executive_report.aggregators.http_adaptive import build_http_adaptive_section
from cloudflare_executive_report.aggregators.security import build_security_section

SectionBuilder = Callable[..., dict[str, Any]]

SECTION_BUILDERS: dict[str, SectionBuilder] = {
    "dns": build_dns_section,
    "http": build_http_section,
    "http_adaptive": build_http_adaptive_section,
    "security": build_security_section,
    "cache": build_cache_section,
    "email": build_email_section,
    "dns_records": build_dns_records_section,
    "audit": build_audit_section,
    "certificates": build_certificates_section,
}
