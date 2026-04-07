from cloudflare_executive_report.config import AppConfig


def test_default_output_dir_separate_from_cache():
    cfg = AppConfig()
    assert cfg.output_dir == "~/.cf-report"
    assert cfg.cache_dir == "~/.cache/cf-report"
    assert str(cfg.report_outputs_dir()).endswith("/.cf-report/outputs")
