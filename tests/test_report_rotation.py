from datetime import date

from cloudflare_executive_report.config import AppConfig
from cloudflare_executive_report.sync.orchestrator import _rotate_report_outputs


def test_rotate_report_outputs_creates_previous_and_history(tmp_path):
    cfg = AppConfig(
        api_token="x",
        cache_dir=str(tmp_path / "cache"),
        output_dir=str(tmp_path / "out"),
    )
    current = cfg.report_current_path()
    current.parent.mkdir(parents=True, exist_ok=True)
    current.write_text('{"zones":[]}', encoding="utf-8")

    _rotate_report_outputs(cfg, history_date=date(2026, 4, 7))

    previous = cfg.report_previous_path()
    history_files = list(cfg.report_history_dir().glob("cf_report_*.json"))
    assert previous.is_file()
    assert len(history_files) == 1
    history = history_files[0]
    assert previous.read_text(encoding="utf-8") == '{"zones":[]}'
    assert history.read_text(encoding="utf-8") == '{"zones":[]}'
