"""Configuration file (~/.cf-report/config.yaml)."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, cast

import yaml

from cloudflare_executive_report.common.constants import PROJECT_NAME
from cloudflare_executive_report.pdf.figure_quality import parse_pdf_image_quality

CONFIG_DIR_NAME = ".cf-report"
CONFIG_FILE_NAME = "config.yaml"

DEFAULT_EMAIL_SUBJECT_TEMPLATE = f"{PROJECT_NAME} - {{date}}"
DEFAULT_EMAIL_BODY_TEMPLATE = (
    "Hello,\n\n"
    f"Attached is the {PROJECT_NAME} for {{period}} ({{zone_count}} zone(s)).\n\n"
    "Regards,\n"
    "Cloudflare Report Tool\n"
)
_HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def parse_hex_color(
    raw: str | None,
    *,
    field_name: str,
    default: str,
) -> str:
    """Return normalized #RRGGBB color or raise ValueError."""
    value = (raw or default).strip()
    if not _HEX_COLOR_RE.fullmatch(value):
        msg = f"{field_name} must be a hex color like '#RRGGBB' (got {raw!r})"
        raise ValueError(msg)
    return value


def default_config_path() -> Path:
    if os.name == "nt":
        base = os.environ.get("USERPROFILE", "")
        if not base:
            base = str(Path.home())
        return Path(base) / CONFIG_DIR_NAME / CONFIG_FILE_NAME
    return Path.home() / CONFIG_DIR_NAME / CONFIG_FILE_NAME


def expand_path(s: str) -> Path:
    return Path(os.path.expanduser(s)).resolve()


def parse_pdf_image_format(
    raw: str | None,
    *,
    field_name: str,
    default: Literal["png", "svg"] = "png",
) -> Literal["png", "svg"]:
    value = (raw or default).strip().lower()
    if value not in {"png", "svg"}:
        msg = f"{field_name} must be png or svg (got {raw!r})"
        raise ValueError(msg)
    return cast(Literal["png", "svg"], value)


def parse_pdf_profile(
    raw: str | None,
    *,
    field_name: str = "pdf.profile",
) -> Literal["minimal", "executive", "detailed"]:
    """Return validated PDF output profile (report length preset)."""
    value = (raw or "executive").strip().lower()
    if value not in {"minimal", "executive", "detailed"}:
        msg = f"{field_name} must be minimal, executive, or detailed (got {value!r})"
        raise ValueError(msg)
    return cast(Literal["minimal", "executive", "detailed"], value)


@dataclass
class ZoneEntry:
    id: str
    name: str


@dataclass
class CoverConfig:
    enabled: bool = True
    company_name: str = ""
    logo_path: str = ""
    title: str = PROJECT_NAME
    subtitle: str = "Security & Performance Overview"
    notes: str = ""
    prepared_for: str = ""
    classification: str = ""
    date_format: str = "%d/%b/%Y"

    def resolved_logo_path(self) -> Path | None:
        raw = self.logo_path.strip()
        if not raw:
            return None
        try:
            return expand_path(raw)
        except Exception:
            return None


@dataclass
class PdfConfig:
    """PDF rendering options."""

    image_quality: str = "medium"
    chart_format: Literal["png", "svg"] = "png"
    map_format: Literal["png", "svg"] = "png"
    profile: Literal["minimal", "executive", "detailed"] = "executive"
    primary_color: str = "#2563eb"
    accent_color: str = "#f38020"


@dataclass
class ExecutiveConfig:
    """Executive summary generation options."""

    disabled_rules: list[str] = field(default_factory=list)
    include_appendix: bool = True
    reference_risk_weight: int = 60
    verdict_warn_threshold: int = 3


@dataclass
class EmailConfig:
    """SMTP settings and message templates for optional PDF delivery."""

    enabled: bool = False
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_ssl: bool = False
    smtp_starttls: bool = True
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    recipients: list[str] = field(default_factory=list)
    subject: str = DEFAULT_EMAIL_SUBJECT_TEMPLATE
    body: str = DEFAULT_EMAIL_BODY_TEMPLATE


@dataclass
class PortfolioConfig:
    """Multi-zone portfolio summary options."""

    sort_by: Literal["score", "zone_name"] = "score"


@dataclass
class AppConfig:
    """Application settings loaded from config.yaml."""

    api_token: str = ""
    cache_dir: str = "~/.cache/cf-report"
    output_dir: str = "~/.cf-report"
    default_zone: str = ""
    log_level: str = "info"
    default_period: str = "last_month"
    types: list[str] = field(default_factory=list)
    zones: list[ZoneEntry] = field(default_factory=list)
    pdf: PdfConfig = field(default_factory=PdfConfig)
    executive: ExecutiveConfig = field(default_factory=ExecutiveConfig)
    email: EmailConfig = field(default_factory=EmailConfig)
    portfolio: PortfolioConfig = field(default_factory=PortfolioConfig)
    cover: CoverConfig = field(default_factory=CoverConfig)

    def cache_path(self) -> Path:
        return expand_path(self.cache_dir)

    def output_path(self) -> Path:
        return expand_path(self.output_dir)

    def report_outputs_dir(self) -> Path:
        return self.output_path() / "outputs"

    def report_current_path(self) -> Path:
        return self.report_outputs_dir() / "cf_report.json"

    def report_previous_path(self) -> Path:
        return self.report_outputs_dir() / "cf_report.previous.json"

    def report_history_dir(self) -> Path:
        return self.report_outputs_dir() / "history"

    def to_yaml_dict(self) -> dict[str, Any]:
        return {
            "api_token": self.api_token,
            "cache_dir": self.cache_dir,
            "output_dir": self.output_dir,
            "default_zone": self.default_zone,
            "log_level": self.log_level,
            "default_period": self.default_period,
            "types": list(self.types),
            "zones": [{"id": z.id, "name": z.name} for z in self.zones],
            "pdf": {
                "image_quality": self.pdf.image_quality,
                "chart_format": self.pdf.chart_format,
                "map_format": self.pdf.map_format,
                "profile": self.pdf.profile,
                "colors": {
                    "primary": self.pdf.primary_color,
                    "accent": self.pdf.accent_color,
                },
            },
            "executive": {
                "disabled_rules": list(self.executive.disabled_rules),
                "include_appendix": self.executive.include_appendix,
                "reference_risk_weight": self.executive.reference_risk_weight,
                "verdict_warn_threshold": self.executive.verdict_warn_threshold,
            },
            "email": {
                "enabled": self.email.enabled,
                "smtp_host": self.email.smtp_host,
                "smtp_port": self.email.smtp_port,
                "smtp_ssl": self.email.smtp_ssl,
                "smtp_starttls": self.email.smtp_starttls,
                "smtp_user": self.email.smtp_user,
                "smtp_password": self.email.smtp_password,
                "smtp_from": self.email.smtp_from,
                "recipients": list(self.email.recipients),
                "subject": self.email.subject,
                "body": self.email.body,
            },
            "portfolio": {
                "sort_by": self.portfolio.sort_by,
            },
            "cover": {
                "enabled": self.cover.enabled,
                "company_name": self.cover.company_name,
                "logo_path": self.cover.logo_path,
                "title": self.cover.title,
                "subtitle": self.cover.subtitle,
                "notes": self.cover.notes,
                "prepared_for": self.cover.prepared_for,
                "classification": self.cover.classification,
                "date_format": self.cover.date_format,
            },
        }

    @classmethod
    def from_yaml_dict(cls, data: dict[str, Any]) -> AppConfig:
        if not isinstance(data, dict):
            raise ValueError("Config root must be a mapping")
        zones_raw = data.get("zones") or []
        zones = [ZoneEntry(id=str(z["id"]), name=str(z["name"])) for z in zones_raw]

        pdf_raw = data.get("pdf") or {}
        if not isinstance(pdf_raw, dict):
            raise ValueError("pdf must be a mapping")
        pq_raw = pdf_raw.get("image_quality")
        pdf_image_quality = parse_pdf_image_quality(
            str(pq_raw) if pq_raw is not None else None
        ).value
        pcf_raw = pdf_raw.get("chart_format")
        pdf_chart_format = parse_pdf_image_format(
            str(pcf_raw) if pcf_raw is not None else None,
            field_name="pdf.chart_format",
        )
        pmf_raw = pdf_raw.get("map_format")
        pdf_map_format = parse_pdf_image_format(
            str(pmf_raw) if pmf_raw is not None else None,
            field_name="pdf.map_format",
        )
        pdf_profile_raw = pdf_raw.get("profile")
        pdf_profile = parse_pdf_profile(
            str(pdf_profile_raw) if pdf_profile_raw is not None else None,
        )
        pdf_colors_raw = pdf_raw.get("colors") or {}
        if not isinstance(pdf_colors_raw, dict):
            raise ValueError("pdf.colors must be a mapping")
        pdf_primary_color = parse_hex_color(
            str(pdf_colors_raw.get("primary"))
            if pdf_colors_raw.get("primary") is not None
            else None,
            field_name="pdf.colors.primary",
            default="#2563eb",
        )
        pdf_accent_color = parse_hex_color(
            str(pdf_colors_raw.get("accent")) if pdf_colors_raw.get("accent") is not None else None,
            field_name="pdf.colors.accent",
            default="#f38020",
        )

        executive_raw = data.get("executive") or {}
        if not isinstance(executive_raw, dict):
            raise ValueError("executive must be a mapping")
        raw_disabled_rules = executive_raw.get("disabled_rules")
        if isinstance(raw_disabled_rules, list):
            disabled_rules = [str(x) for x in raw_disabled_rules]
        else:
            disabled_rules = []
        raw_include_appendix = executive_raw.get("include_appendix")
        include_appendix = True if raw_include_appendix is None else bool(raw_include_appendix)
        reference_risk_weight = int(executive_raw.get("reference_risk_weight") or 60)
        verdict_warn_threshold = int(executive_raw.get("verdict_warn_threshold") or 3)

        email_raw = data.get("email") or {}
        if not isinstance(email_raw, dict):
            raise ValueError("email must be a mapping")
        email_enabled = bool(email_raw.get("enabled", False))
        smtp_ssl = bool(email_raw.get("smtp_ssl", False))
        raw_starttls = email_raw.get("smtp_starttls")
        if smtp_ssl:
            smtp_starttls = False if raw_starttls is None else bool(raw_starttls)
        else:
            smtp_starttls = True if raw_starttls is None else bool(raw_starttls)
        if smtp_ssl and smtp_starttls:
            raise ValueError("email.smtp_ssl and email.smtp_starttls cannot both be true")
        raw_recipients = email_raw.get("recipients")
        recipients = [str(x) for x in raw_recipients] if isinstance(raw_recipients, list) else []
        smtp_port_raw = email_raw.get("smtp_port")
        smtp_port = int(smtp_port_raw) if smtp_port_raw is not None else 587
        raw_subject = email_raw.get("subject")
        email_subject = DEFAULT_EMAIL_SUBJECT_TEMPLATE if raw_subject is None else str(raw_subject)
        raw_body = email_raw.get("body")
        email_body = DEFAULT_EMAIL_BODY_TEMPLATE if raw_body is None else str(raw_body)

        portfolio_raw = data.get("portfolio") or {}
        if not isinstance(portfolio_raw, dict):
            raise ValueError("portfolio must be a mapping")
        sort_by_raw = str(portfolio_raw.get("sort_by") or "score").strip().lower()
        if sort_by_raw not in {"score", "zone_name"}:
            raise ValueError(f"portfolio.sort_by must be score or zone_name (got {sort_by_raw!r})")

        cover_raw = data.get("cover") or {}
        if not isinstance(cover_raw, dict):
            raise ValueError("cover must be a mapping")
        cover = CoverConfig(
            enabled=bool(cover_raw.get("enabled", True)),
            company_name=str(cover_raw.get("company_name") or ""),
            logo_path=str(cover_raw.get("logo_path") or ""),
            title=str(cover_raw.get("title") or PROJECT_NAME),
            subtitle=str(cover_raw.get("subtitle") or "Security & Performance Overview"),
            notes=str(cover_raw.get("notes") or ""),
            prepared_for=str(cover_raw.get("prepared_for") or ""),
            classification=str(cover_raw.get("classification") or ""),
            date_format=str(cover_raw.get("date_format") or "%d/%b/%Y"),
        )

        raw_types = data.get("types")
        if isinstance(raw_types, list):
            types = [str(value) for value in raw_types]
        else:
            types = []

        return cls(
            api_token=str(data.get("api_token") or ""),
            cache_dir=str(data.get("cache_dir") or "~/.cache/cf-report"),
            output_dir=str(data.get("output_dir") or "~/.cf-report"),
            default_zone=str(data.get("default_zone") or ""),
            log_level=str(data.get("log_level") or "info"),
            default_period=str(data.get("default_period") or "last_month"),
            types=types,
            zones=zones,
            pdf=PdfConfig(
                image_quality=pdf_image_quality,
                chart_format=pdf_chart_format,
                map_format=pdf_map_format,
                profile=pdf_profile,
                primary_color=pdf_primary_color,
                accent_color=pdf_accent_color,
            ),
            executive=ExecutiveConfig(
                disabled_rules=disabled_rules,
                include_appendix=include_appendix,
                reference_risk_weight=reference_risk_weight,
                verdict_warn_threshold=verdict_warn_threshold,
            ),
            email=EmailConfig(
                enabled=email_enabled,
                smtp_host=str(email_raw.get("smtp_host") or ""),
                smtp_port=smtp_port,
                smtp_ssl=smtp_ssl,
                smtp_starttls=smtp_starttls,
                smtp_user=str(email_raw.get("smtp_user") or ""),
                smtp_password=str(email_raw.get("smtp_password") or ""),
                smtp_from=str(email_raw.get("smtp_from") or ""),
                recipients=recipients,
                subject=email_subject,
                body=email_body,
            ),
            portfolio=PortfolioConfig(sort_by=cast(Literal["score", "zone_name"], sort_by_raw)),
            cover=cover,
        )


def load_config(path: Path | None = None) -> AppConfig:
    """Load config from ``path`` or default ``~/.cf-report/config.yaml``."""
    p = path or default_config_path()
    if not p.is_file():
        raise FileNotFoundError(f"Config not found: {p}")
    with p.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError("Config root must be a mapping")
    return AppConfig.from_yaml_dict(data)


def save_config(cfg: AppConfig, path: Path | None = None) -> None:
    p = path or default_config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        yaml.safe_dump(
            cfg.to_yaml_dict(),
            f,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )


def save_config_template(cfg: AppConfig, path: Path | None = None) -> None:
    """Write config template YAML with explanatory comments."""
    p = path or default_config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    body = yaml.safe_dump(
        cfg.to_yaml_dict(),
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
    )
    lines = [
        "# Core settings",
        "# default_zone is used when CLI --zone is omitted",
        "# default_period is reserved for future period presets",
        "#",
        "# Sections:",
        "# - pdf: PDF generation options (profile: minimal | executive | detailed)",
        "# - executive: executive summary behavior",
        "# - email: optional SMTP delivery (use cf-report report --email when enabled)",
        "# - portfolio: multi-zone summary ordering",
        "# - cover: cover page text and branding",
        "",
        body.rstrip(),
        "",
    ]
    p.write_text("\n".join(lines), encoding="utf-8")


def template_config() -> AppConfig:
    return AppConfig(
        api_token="cfat_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
        cache_dir="~/.cache/cf-report",
        output_dir="~/.cf-report",
        default_zone="",
        log_level="info",
        default_period="last_month",
        types=[],
        zones=[],
        pdf=PdfConfig(
            image_quality="medium",
            chart_format="png",
            map_format="png",
            profile="executive",
            primary_color="#2563eb",
            accent_color="#f38020",
        ),
        executive=ExecutiveConfig(
            disabled_rules=[],
            include_appendix=True,
            reference_risk_weight=60,
            verdict_warn_threshold=3,
        ),
        email=EmailConfig(),
        portfolio=PortfolioConfig(sort_by="score"),
        cover=CoverConfig(),
    )
