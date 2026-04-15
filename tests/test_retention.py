from datetime import date

from cloudflare_executive_report.common.retention import (
    date_outside_dns_retention,
    dns_retention_days,
    http_retention_days,
    security_retention_days,
)


def test_dns_retention_days():
    assert dns_retention_days("free") == 7
    assert dns_retention_days("pro") == 31
    assert dns_retention_days("enterprise") == 62


def test_http_retention_days():
    assert http_retention_days("free") == 30
    assert http_retention_days("enterprise") == 30


def test_security_retention_days_by_plan():
    assert security_retention_days("free") == 7
    assert security_retention_days("pro") == 7
    assert security_retention_days("business") == 31
    assert security_retention_days("enterprise") == 90


def test_date_outside():
    ref = date(2026, 4, 10)
    assert date_outside_dns_retention(date(2026, 4, 3), 7, ref=ref) is False
    assert date_outside_dns_retention(date(2026, 4, 2), 7, ref=ref) is True
