from datetime import date

from cloudflare_executive_report.config import AppConfig
from cloudflare_executive_report.sync.orchestrator import run_clean


def test_run_clean_history_parsing_old_and_new(tmp_path):
    cfg = AppConfig(
        api_token="x",
        cache_dir=str(tmp_path / "cache"),
        history_dir=str(tmp_path / "out"),
    )
    hist_dir = cfg.history_path()
    hist_dir.mkdir(parents=True)

    # 1. Old format: cf_report_YYYY-MM-DD_HHMMSS.json
    old_file = hist_dir / "cf_report_2026-01-01_120000.json"
    old_file.write_text("{}")

    # 2. New format: cf_report_<hash>_YYYY-MM-DD_HHMMSS.json
    # Hash is exactly 16 chars
    new_file = hist_dir / "cf_report_abcdef0123456789_2026-01-01_120000.json"
    new_file.write_text("{}")

    # 3. New format file that should NOT be deleted (too recent)
    recent_file = hist_dir / "cf_report_abcdef0123456789_2026-04-20_120000.json"
    recent_file.write_text("{}")

    # Clean older than 30 days (relative to 2026-04-20)
    # We need to mock utc_today to ensure predictable behavior
    from unittest.mock import patch

    with patch(
        "cloudflare_executive_report.sync.orchestrator.utc_today", return_value=date(2026, 4, 20)
    ):
        run_clean(cfg, older_than=30, scope_cache=False, scope_history=True, quiet=True)

    assert not old_file.exists(), "Old format file should have been deleted"
    assert not new_file.exists(), "New format file should have been deleted"
    assert recent_file.exists(), "Recent file should NOT have been deleted"
