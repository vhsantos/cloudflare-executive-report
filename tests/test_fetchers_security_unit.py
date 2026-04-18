"""Unit tests for fetchers/security.py."""

from __future__ import annotations

from cloudflare_executive_report.fetchers.security import (
    _fold_eyeball_matrix,
)


def test_fold_eyeball_matrix_basic() -> None:
    # row: count, dimensions: {securityAction, cacheStatus}
    rows = [
        {"count": 10, "dimensions": {"securityAction": "block", "cacheStatus": "miss"}},
        {"count": 20, "dimensions": {"securityAction": "allow", "cacheStatus": "hit"}},
        {"count": 30, "dimensions": {"securityAction": "allow", "cacheStatus": "dynamic"}},
    ]
    mitigated, cf, origin = _fold_eyeball_matrix(rows)
    # mitigated = 10 (block)
    # cf = 20 (allow + hit)
    # origin = 30 (allow + dynamic)
    assert mitigated == 10
    assert cf == 20
    assert origin == 30


def test_fold_eyeball_matrix_mixed() -> None:
    rows = [
        {"count": 5, "dimensions": {"securityAction": "js_challenge", "cacheStatus": "hit"}},
        {"count": 15, "dimensions": {"securityAction": "allow", "cacheStatus": "bypass"}},
        {"count": 25, "dimensions": {"securityAction": "unknown", "cacheStatus": "none"}},
    ]
    mitigated, cf, origin = _fold_eyeball_matrix(rows)
    # mitigated = 5 (js_challenge)
    # cf = 25 (unknown + none)
    # origin = 15 (allow + bypass)
    assert mitigated == 5
    assert cf == 25
    assert origin == 15
