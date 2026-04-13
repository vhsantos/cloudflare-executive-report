from cloudflare_executive_report.config import AppConfig, ExecutiveConfig, save_config_template


def test_default_output_dir_separate_from_cache():
    cfg = AppConfig()
    assert cfg.output_dir == "~/.cf-report"
    assert cfg.cache_dir == "~/.cache/cf-report"
    assert str(cfg.report_outputs_dir()).endswith("/.cf-report/outputs")


def test_from_yaml_dict_ignore_messages() -> None:
    cfg = AppConfig.from_yaml_dict(
        {
            "zones": [],
            "executive": {"ignore_messages": ["review_dnssec", r"^ssl_"]},
        }
    )
    assert cfg.executive.ignore_messages == ["review_dnssec", r"^ssl_"]


def test_to_yaml_dict_round_trip_ignore_messages() -> None:
    cfg = AppConfig(executive=ExecutiveConfig(ignore_messages=["plan_tls_renewal"]))
    back = AppConfig.from_yaml_dict(cfg.to_yaml_dict())
    assert back.executive.ignore_messages == ["plan_tls_renewal"]


def test_pdf_include_nist_appendix_yaml_round_trip() -> None:
    cfg = AppConfig(executive=ExecutiveConfig(include_nist_appendix=False))
    back = AppConfig.from_yaml_dict(cfg.to_yaml_dict())
    assert back.executive.include_nist_appendix is False
    default_back = AppConfig.from_yaml_dict({"zones": []})
    assert default_back.executive.include_nist_appendix is True


def test_save_config_template_includes_comments_and_sections(tmp_path) -> None:
    out = tmp_path / "config.yaml"
    save_config_template(AppConfig(), out)
    text = out.read_text(encoding="utf-8")
    assert "# Core settings" in text
    assert "pdf:" in text
    assert "executive:" in text
    assert "email:" in text
