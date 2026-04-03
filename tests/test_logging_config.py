import logging

from cloudflare_executive_report.logging_config import effective_debug_enabled, setup_logging


def test_log_level_debug_same_as_verbose_for_effective_debug():
    setup_logging(verbose=False, quiet=False, log_level="debug")
    assert effective_debug_enabled()
    assert logging.getLogger("httpx").level == logging.DEBUG


def test_verbose_sets_debug():
    setup_logging(verbose=True, quiet=False, log_level="info")
    assert effective_debug_enabled()


def test_info_not_debug():
    setup_logging(verbose=False, quiet=False, log_level="info")
    assert not effective_debug_enabled()
    assert logging.getLogger("httpx").level == logging.WARNING
