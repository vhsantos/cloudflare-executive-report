import sys
from unittest import mock

import pytest
from click.exceptions import Exit

from cloudflare_executive_report import exits
from cloudflare_executive_report.cli import _check_last_argv


def test_check_last_requires_number():
    with mock.patch.object(sys, "argv", ["cf-report", "sync", "--last"]):
        with pytest.raises(Exit) as e:
            _check_last_argv()
        assert e.value.exit_code == exits.INVALID_PARAMS


def test_check_last_ok():
    with mock.patch.object(sys, "argv", ["cf-report", "sync", "--last", "7"]):
        _check_last_argv()
