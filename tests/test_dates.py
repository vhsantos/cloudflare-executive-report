from datetime import date

from cloudflare_executive_report.common.dates import (
    format_ymd,
    iter_dates_inclusive,
    last_n_complete_days,
    parse_ymd,
)


def test_last_n_complete_days():
    y = date(2026, 4, 2)
    s, e = last_n_complete_days(7, yesterday=y)
    assert s == date(2026, 3, 27)
    assert e == y


def test_iter_dates_inclusive():
    days = list(iter_dates_inclusive(date(2026, 3, 1), date(2026, 3, 3)))
    assert len(days) == 3
    assert format_ymd(days[0]) == "2026-03-01"


def test_parse_format_roundtrip():
    d = parse_ymd("2026-01-15")
    assert format_ymd(d) == "2026-01-15"
