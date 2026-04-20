import pytest

from cloudflare_executive_report.config import (
    AppConfig,
    EmailConfig,
    ExecutiveConfig,
    PdfConfig,
    PortfolioConfig,
    save_config_template,
)


def test_default_history_dir_separate_from_cache():
    cfg = AppConfig()
    assert cfg.history_dir == "~/.cf-report"
    assert cfg.cache_dir == "~/.cache/cf-report"
    assert str(cfg.history_path()).endswith("/.cf-report")


def test_from_yaml_dict_disabled_rules() -> None:
    cfg = AppConfig.from_yaml_dict(
        {
            "zones": [],
            "executive": {"disabled_rules": ["dnssec", r"^ssl_"]},
        }
    )
    assert cfg.executive.disabled_rules == ["dnssec", r"^ssl_"]


def test_api_token_from_env_when_missing(monkeypatch) -> None:
    monkeypatch.setenv("CF_REPORT_API_TOKEN", "cfat_env_token")
    cfg = AppConfig.from_yaml_dict({"zones": []})
    assert cfg.api_token == "cfat_env_token"


def test_api_token_empty_string_uses_env(monkeypatch) -> None:
    monkeypatch.setenv("CF_REPORT_API_TOKEN", "cfat_env_token")
    cfg = AppConfig.from_yaml_dict({"api_token": "", "zones": []})
    assert cfg.api_token == "cfat_env_token"


def test_api_token_env_precedence_cf_report_over_cloudflare(monkeypatch) -> None:
    monkeypatch.setenv("CF_REPORT_API_TOKEN", "cfat_primary")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "cfat_fallback")
    cfg = AppConfig.from_yaml_dict({"zones": []})
    assert cfg.api_token == "cfat_primary"


def test_config_api_token_overrides_env(monkeypatch) -> None:
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "cfat_env_token")
    cfg = AppConfig.from_yaml_dict({"api_token": "cfat_config_token", "zones": []})
    assert cfg.api_token == "cfat_config_token"


def test_smtp_password_from_env_when_missing(monkeypatch) -> None:
    monkeypatch.setenv("CF_REPORT_SMTP_PASSWORD", "smtp_env_password")
    cfg = AppConfig.from_yaml_dict({"zones": [], "email": {"enabled": True, "smtp_host": "x"}})
    assert cfg.email.smtp_password == "smtp_env_password"


def test_config_smtp_password_overrides_env(monkeypatch) -> None:
    monkeypatch.setenv("CF_REPORT_SMTP_PASSWORD", "smtp_env_password")
    cfg = AppConfig.from_yaml_dict(
        {
            "zones": [],
            "email": {"enabled": True, "smtp_host": "x", "smtp_password": "smtp_cfg_password"},
        }
    )
    assert cfg.email.smtp_password == "smtp_cfg_password"


def test_to_yaml_dict_round_trip_disabled_rules() -> None:
    cfg = AppConfig(executive=ExecutiveConfig(disabled_rules=["cert_expire_30"]))
    back = AppConfig.from_yaml_dict(cfg.to_yaml_dict())
    assert back.executive.disabled_rules == ["cert_expire_30"]


def test_pdf_include_appendix_yaml_round_trip() -> None:
    cfg = AppConfig(executive=ExecutiveConfig(include_appendix=False))
    back = AppConfig.from_yaml_dict(cfg.to_yaml_dict())
    assert back.executive.include_appendix is False
    default_back = AppConfig.from_yaml_dict({"zones": []})
    assert default_back.executive.include_appendix is True


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


def test_pdf_profile_yaml_round_trip() -> None:
    cfg = AppConfig(pdf=PdfConfig(profile="minimal"))
    back = AppConfig.from_yaml_dict(cfg.to_yaml_dict())
    assert back.pdf.profile == "minimal"


def test_pdf_profile_defaults_to_executive() -> None:
    cfg = AppConfig.from_yaml_dict({"zones": []})
    assert cfg.pdf.profile == "executive"


def test_pdf_profile_rejects_invalid_value() -> None:
    with pytest.raises(ValueError, match="pdf.profile"):
        AppConfig.from_yaml_dict({"zones": [], "pdf": {"profile": "full"}})


def test_pdf_colors_yaml_round_trip() -> None:
    cfg = AppConfig(
        pdf=PdfConfig(
            profile="executive",
            primary_color="#0f4c81",
            accent_color="#f38020",
        )
    )
    back = AppConfig.from_yaml_dict(cfg.to_yaml_dict())
    assert back.pdf.primary_color == "#0f4c81"
    assert back.pdf.accent_color == "#f38020"


def test_pdf_colors_reject_invalid_hex() -> None:
    with pytest.raises(ValueError, match="pdf.colors.primary"):
        AppConfig.from_yaml_dict({"zones": [], "pdf": {"colors": {"primary": "orange"}}})


def test_email_ssl_and_starttls_both_true_rejected() -> None:
    with pytest.raises(ValueError, match="email.smtp_ssl"):
        AppConfig.from_yaml_dict(
            {
                "zones": [],
                "email": {"smtp_ssl": True, "smtp_starttls": True, "smtp_host": "x"},
            }
        )


def test_email_yaml_round_trip() -> None:
    cfg = AppConfig(
        email=EmailConfig(
            enabled=True,
            smtp_host="smtp.example.com",
            smtp_port=465,
            smtp_ssl=True,
            smtp_starttls=False,
            smtp_user="u@example.com",
            smtp_password="secret",
            smtp_from="Reports <reports@example.com>",
            recipients=["a@b.com"],
            subject="S {{date}}",
            body="B {{period}}",
        )
    )
    back = AppConfig.from_yaml_dict(cfg.to_yaml_dict())
    assert back.email.enabled is True
    assert back.email.smtp_ssl is True
    assert back.email.smtp_starttls is False
    assert back.email.smtp_from.startswith("Reports")
    assert back.email.subject == "S {{date}}"
    assert back.email.body == "B {{period}}"
