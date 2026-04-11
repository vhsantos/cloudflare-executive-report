from cloudflare_executive_report.config import AppConfig


def test_default_output_dir_separate_from_cache():
    cfg = AppConfig()
    assert cfg.output_dir == "~/.cf-report"
    assert cfg.cache_dir == "~/.cache/cf-report"
    assert str(cfg.report_outputs_dir()).endswith("/.cf-report/outputs")


def test_from_yaml_dict_ignore_messages() -> None:
    cfg = AppConfig.from_yaml_dict(
        {
            "zones": [],
            "ignore_messages": ["review_dnssec", r"^ssl_"],
        }
    )
    assert cfg.ignore_messages == ["review_dnssec", r"^ssl_"]


def test_to_yaml_dict_round_trip_ignore_messages() -> None:
    cfg = AppConfig(ignore_messages=["plan_tls_renewal"])
    back = AppConfig.from_yaml_dict(cfg.to_yaml_dict())
    assert back.ignore_messages == ["plan_tls_renewal"]
