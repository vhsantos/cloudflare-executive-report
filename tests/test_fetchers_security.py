"""Security fetcher matrix fold (mitigated vs pass split)."""

from cloudflare_executive_report.fetchers import security as sec


def test_fold_missing_security_action_counts_as_pass_by_cache_status() -> None:
    rows = [
        {"count": 1000, "dimensions": {"cacheStatus": "dynamic"}},
        {"count": 50, "dimensions": {"cacheStatus": "hit"}},
    ]
    m, cf, org = sec._fold_eyeball_matrix(rows)
    assert m == 0
    assert cf == 50
    assert org == 1000


def test_fold_miss_and_bypass_count_as_origin() -> None:
    rows = [
        {"count": 100, "dimensions": {"cacheStatus": "miss"}},
        {"count": 40, "dimensions": {"cacheStatus": "bypass"}},
    ]
    m, cf, org = sec._fold_eyeball_matrix(rows)
    assert m == cf == 0
    assert org == 140


def test_fold_block_counts_mitigated() -> None:
    rows = [
        {"count": 12, "dimensions": {"securityAction": "block", "cacheStatus": "dynamic"}},
    ]
    m, cf, org = sec._fold_eyeball_matrix(rows)
    assert m == 12
    assert cf == org == 0


def test_fold_allow_hit_is_served_cf() -> None:
    rows = [
        {"count": 7, "dimensions": {"securityAction": "allow", "cacheStatus": "hit"}},
    ]
    m, cf, org = sec._fold_eyeball_matrix(rows)
    assert m == org == 0
    assert cf == 7


def test_fold_unknown_and_link_maze_are_pass_not_mitigated() -> None:
    rows = [
        {"count": 100, "dimensions": {"securityAction": "unknown", "cacheStatus": "dynamic"}},
        {"count": 50, "dimensions": {"securityAction": "link_maze_injected", "cacheStatus": "hit"}},
    ]
    m, cf, org = sec._fold_eyeball_matrix(rows)
    assert m == 0
    assert cf == 50
    assert org == 100


def test_fold_js_challenge_counts_mitigated() -> None:
    rows = [
        {"count": 3, "dimensions": {"securityAction": "js_challenge", "cacheStatus": "dynamic"}},
    ]
    m, cf, org = sec._fold_eyeball_matrix(rows)
    assert m == 3
    assert cf == org == 0
