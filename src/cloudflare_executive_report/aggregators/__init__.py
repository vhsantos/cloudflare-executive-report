"""Per-stream report aggregation builders."""

from cloudflare_executive_report.aggregators.audit import build_audit_section
from cloudflare_executive_report.aggregators.cache import build_cache_section
from cloudflare_executive_report.aggregators.certificates import build_certificates_section
from cloudflare_executive_report.aggregators.dns import build_dns_section
from cloudflare_executive_report.aggregators.dns_records import build_dns_records_section
from cloudflare_executive_report.aggregators.http import build_http_section
from cloudflare_executive_report.aggregators.http_adaptive import build_http_adaptive_section
from cloudflare_executive_report.aggregators.registry import SECTION_BUILDERS
from cloudflare_executive_report.aggregators.security import build_security_section

__all__ = [
    "SECTION_BUILDERS",
    "build_audit_section",
    "build_cache_section",
    "build_certificates_section",
    "build_dns_records_section",
    "build_dns_section",
    "build_http_adaptive_section",
    "build_http_section",
    "build_security_section",
]
