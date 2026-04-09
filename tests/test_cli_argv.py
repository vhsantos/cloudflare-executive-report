import sys
from pathlib import Path
from unittest import mock

import pytest
from click.exceptions import Exit

from cloudflare_executive_report import exits
from cloudflare_executive_report.cli import _check_last_argv
from cloudflare_executive_report.report.period import pdf_report_period_for_options
from cloudflare_executive_report.sync.options import SyncMode, SyncOptions


def test_check_last_requires_number():
    with mock.patch.object(sys, "argv", ["cf-report", "sync", "--last"]):
        with pytest.raises(Exit) as e:
            _check_last_argv()
        assert e.value.exit_code == exits.INVALID_PARAMS


def test_check_last_ok():
    with mock.patch.object(sys, "argv", ["cf-report", "sync", "--last", "7"]):
        _check_last_argv()


def test_check_last_ok_for_report():
    with mock.patch.object(sys, "argv", ["cf-report", "report", "--last", "3", "-o", "x.pdf"]):
        _check_last_argv()


def test_check_last_rejects_non_digit():
    with mock.patch.object(sys, "argv", ["cf-report", "sync", "--last", "abc"]):
        with pytest.raises(Exit) as e:
            _check_last_argv()
        assert e.value.exit_code == exits.INVALID_PARAMS


def test_check_last_rejects_negative_token():
    with mock.patch.object(sys, "argv", ["cf-report", "sync", "--last", "-1"]):
        with pytest.raises(Exit) as e:
            _check_last_argv()
        assert e.value.exit_code == exits.INVALID_PARAMS


def _minimal_cfg_for_period() -> mock.MagicMock:
    cfg = mock.MagicMock()
    cfg.cache_path.return_value = Path("/nonexistent/cache")
    z = mock.MagicMock()
    z.id = "z1"
    z.name = "example.com"
    cfg.zones = [z]
    return cfg


def test_pdf_report_period_last_one_day():
    opts = SyncOptions(
        mode=SyncMode.last_n,
        last_n=1,
        include_today=False,
        quiet=True,
        types=frozenset({"dns"}),
    )
    s, e = pdf_report_period_for_options(_minimal_cfg_for_period(), opts, zone_filter=None)
    assert s == e


def test_pdf_report_period_explicit_range():
    opts = SyncOptions(
        mode=SyncMode.range,
        start="2026-01-01",
        end="2026-01-07",
        include_today=False,
        quiet=True,
        types=frozenset({"dns"}),
    )
    s, e = pdf_report_period_for_options(_minimal_cfg_for_period(), opts, zone_filter=None)
    assert s == "2026-01-01" and e == "2026-01-07"
