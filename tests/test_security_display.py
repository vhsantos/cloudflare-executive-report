"""Security PDF display label mapping."""

from cloudflare_executive_report.pdf.security_display import (
    format_cache_status_label,
    format_security_action_label,
    format_security_source_label,
)


def test_security_action_dashboard_names() -> None:
    assert format_security_action_label("managed_challenge") == "Managed Challenge"
    assert format_security_action_label("block") == "Block"
    assert format_security_action_label("link_maze_injected") == "AI Labyrinth Served"


def test_security_source_dashboard_names() -> None:
    assert format_security_source_label("botFight") == "Bot fight mode"
    assert format_security_source_label("firewallManaged") == "Managed rules"
    assert format_security_source_label("bic") == "Browser Integrity Check"
    assert format_security_source_label("hot") == "Hotlink Protection"


def test_cache_status_like_dashboard() -> None:
    assert format_cache_status_label("none") == "None"
    assert format_cache_status_label("hit") == "Hit"
    assert format_cache_status_label("dynamic") == "Dynamic"
