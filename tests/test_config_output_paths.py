import pytest

from cloudflare_executive_report.config import (
    AppConfig,
    ExecutiveConfig,
    PortfolioConfig,
    save_config_template,
)


def test_default_output_dir_separate_from_cache():
    cfg = AppConfig()
    assert cfg.output_dir == "~/.cf-report"
    assert cfg.cache_dir == "~/.cache/cf-report"
    assert str(cfg.report_outputs_dir()).endswith("/.cf-report/outputs")


def test_from_yaml_dict_disabled_rules() -> None:
    cfg = AppConfig.from_yaml_dict(
        {
            "zones": [],
            "executive": {"disabled_rules": ["review_dnssec", r"^ssl_"]},
        }
    )
    assert cfg.executive.disabled_rules == ["review_dnssec", r"^ssl_"]


def test_to_yaml_dict_round_trip_disabled_rules() -> None:
    cfg = AppConfig(executive=ExecutiveConfig(disabled_rules=["plan_tls_renewal"]))
    back = AppConfig.from_yaml_dict(cfg.to_yaml_dict())
    assert back.executive.disabled_rules == ["plan_tls_renewal"]


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
    assert "portfolio:" in text


def test_portfolio_sort_by_yaml_round_trip() -> None:
    cfg = AppConfig(portfolio=PortfolioConfig(sort_by="zone_name"))
    back = AppConfig.from_yaml_dict(cfg.to_yaml_dict())
    assert back.portfolio.sort_by == "zone_name"


def test_portfolio_sort_by_rejects_invalid_value() -> None:
    with pytest.raises(ValueError, match="portfolio.sort_by"):
        AppConfig.from_yaml_dict({"zones": [], "portfolio": {"sort_by": "critical_risks"}})
