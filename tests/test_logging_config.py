import logging

from cloudflare_executive_report.common.logging_config import (
    TRACE,
    effective_debug_enabled,
    setup_logging,
)


def test_log_level_debug_same_as_verbose_for_effective_debug():
    # log_level="debug" is level 10
    setup_logging(verbose_count=0, quiet=False, log_level="debug")
    assert effective_debug_enabled()
    # TRACE is 5, but httpx is set to WARNING unless level <= TRACE
    assert logging.getLogger("httpx").level == logging.WARNING


def test_verbose_sets_info():
    setup_logging(verbose_count=1, quiet=False, log_level="warning")
    assert not effective_debug_enabled()
    assert logging.getLogger().level == logging.INFO


def test_verbose_vv_sets_debug():
    setup_logging(verbose_count=2, quiet=False, log_level="warning")
    assert effective_debug_enabled()
    assert logging.getLogger().level == logging.DEBUG


def test_verbose_vvv_sets_trace():
    setup_logging(verbose_count=3, quiet=False, log_level="warning")
    assert effective_debug_enabled()
    assert logging.getLogger().level == TRACE
    assert logging.getLogger("httpx").level == TRACE


def test_quiet_sets_error():
    setup_logging(verbose_count=3, quiet=True, log_level="debug")
    assert not effective_debug_enabled()
    assert logging.getLogger().level == logging.ERROR


def test_default_is_warning():
    setup_logging(verbose_count=0, quiet=False, log_level="warning")
    assert logging.getLogger().level == logging.WARNING
