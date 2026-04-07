from pathlib import Path

from cloudflare_executive_report import exits
from cloudflare_executive_report.config import AppConfig
from cloudflare_executive_report.sync.orchestrator import run_clean


def _cfg(tmp_path: Path) -> AppConfig:
    return AppConfig(
        api_token="x",
        cache_dir=str(tmp_path / "cache"),
        output_dir=str(tmp_path / "out"),
    )


def test_run_clean_scope_history_all(tmp_path: Path):
    cfg = _cfg(tmp_path)
    history_dir = cfg.report_history_dir()
    history_dir.mkdir(parents=True, exist_ok=True)
    (history_dir / "cf_report_2026-01-01.json").write_text("{}", encoding="utf-8")
    code = run_clean(
        cfg,
        older_than=None,
        scope_cache=False,
        scope_history=True,
        quiet=True,
    )
    assert code == exits.SUCCESS
    assert not history_dir.exists()


def test_run_clean_scope_history_older_than(tmp_path: Path):
    cfg = _cfg(tmp_path)
    history_dir = cfg.report_history_dir()
    history_dir.mkdir(parents=True, exist_ok=True)
    old_file = history_dir / "cf_report_2020-01-01.json"
    new_file = history_dir / "cf_report_2099-01-01.json"
    old_file.write_text("{}", encoding="utf-8")
    new_file.write_text("{}", encoding="utf-8")
    code = run_clean(
        cfg,
        older_than=30,
        scope_cache=False,
        scope_history=True,
        quiet=True,
    )
    assert code == exits.SUCCESS
    assert not old_file.exists()
    assert new_file.exists()


def test_run_clean_scope_history_older_than_with_timestamp_filenames(tmp_path: Path):
    cfg = _cfg(tmp_path)
    history_dir = cfg.report_history_dir()
    history_dir.mkdir(parents=True, exist_ok=True)
    old_file = history_dir / "cf_report_2020-01-01_010203.json"
    new_file = history_dir / "cf_report_2099-01-01_010203.json"
    old_file.write_text("{}", encoding="utf-8")
    new_file.write_text("{}", encoding="utf-8")
    code = run_clean(
        cfg,
        older_than=30,
        scope_cache=False,
        scope_history=True,
        quiet=True,
    )
    assert code == exits.SUCCESS
    assert not old_file.exists()
    assert new_file.exists()
