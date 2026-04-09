from typer.testing import CliRunner

from cloudflare_executive_report import exits
from cloudflare_executive_report.cli import app
from cloudflare_executive_report.config import AppConfig


def test_clean_requires_scope(monkeypatch):
    monkeypatch.setattr("cloudflare_executive_report.cli.load_config", lambda: AppConfig())
    monkeypatch.setattr(
        "cloudflare_executive_report.cli.setup_logging",
        lambda **kwargs: None,
    )
    runner = CliRunner()
    result = runner.invoke(app, ["clean"])
    assert result.exit_code == exits.INVALID_PARAMS
    assert "specify --cache, --history, or --all" in result.output


def test_clean_all_maps_to_both_scopes(monkeypatch):
    calls = {}

    def _fake_run_clean(cfg, *, older_than, scope_cache, scope_history, quiet):
        calls["older_than"] = older_than
        calls["scope_cache"] = scope_cache
        calls["scope_history"] = scope_history
        return exits.SUCCESS

    monkeypatch.setattr("cloudflare_executive_report.cli.load_config", lambda: AppConfig())
    monkeypatch.setattr(
        "cloudflare_executive_report.cli.setup_logging",
        lambda **kwargs: None,
    )
    monkeypatch.setattr("cloudflare_executive_report.cli.run_clean", _fake_run_clean)
    runner = CliRunner()
    result = runner.invoke(app, ["clean", "--all", "--force", "--older-than", "7"])
    assert result.exit_code == exits.SUCCESS
    assert calls["older_than"] == 7
    assert calls["scope_cache"] is True
    assert calls["scope_history"] is True


def test_clean_all_requires_force(monkeypatch):
    monkeypatch.setattr("cloudflare_executive_report.cli.load_config", lambda: AppConfig())
    monkeypatch.setattr(
        "cloudflare_executive_report.cli.setup_logging",
        lambda **kwargs: None,
    )
    runner = CliRunner()
    result = runner.invoke(app, ["clean", "--all"])
    assert result.exit_code == exits.INVALID_PARAMS
    assert "--all requires --force" in result.output
