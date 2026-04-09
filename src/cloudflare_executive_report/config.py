"""Configuration file (~/.cf-report/config.yaml)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from cloudflare_executive_report.pdf.figure_quality import parse_pdf_image_quality

CONFIG_DIR_NAME = ".cf-report"
CONFIG_FILE_NAME = "config.yaml"


def default_config_path() -> Path:
    if os.name == "nt":
        base = os.environ.get("USERPROFILE", "")
        if not base:
            base = str(Path.home())
        return Path(base) / CONFIG_DIR_NAME / CONFIG_FILE_NAME
    return Path.home() / CONFIG_DIR_NAME / CONFIG_FILE_NAME


def expand_path(s: str) -> Path:
    return Path(os.path.expanduser(s)).resolve()


@dataclass
class ZoneEntry:
    id: str
    name: str


@dataclass
class CoverConfig:
    enabled: bool = True
    company_name: str = ""
    logo_path: str = ""
    title: str = "Cloudflare Executive Report"
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
class AppConfig:
    api_token: str = ""
    cache_dir: str = "~/.cache/cf-report"
    output_dir: str = "~/.cf-report"
    default_zone: str = ""
    log_level: str = "info"
    # low | medium | high - matplotlib DPI for PDF maps/charts (smaller file vs sharper plots)
    pdf_image_quality: str = "medium"
    zones: list[ZoneEntry] = field(default_factory=list)
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
            "pdf_image_quality": self.pdf_image_quality,
            "zones": [{"id": z.id, "name": z.name} for z in self.zones],
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
        zones_raw = data.get("zones") or []
        zones = [ZoneEntry(id=str(z["id"]), name=str(z["name"])) for z in zones_raw]
        pq_raw = data.get("pdf_image_quality")
        pdf_image_quality = parse_pdf_image_quality(
            str(pq_raw) if pq_raw is not None else None
        ).value
        cover_raw = data.get("cover") or {}
        if not isinstance(cover_raw, dict):
            cover_raw = {}
        cover = CoverConfig(
            enabled=bool(cover_raw.get("enabled", True)),
            company_name=str(cover_raw.get("company_name") or ""),
            logo_path=str(cover_raw.get("logo_path") or ""),
            title=str(cover_raw.get("title") or "Cloudflare Executive Report"),
            subtitle=str(cover_raw.get("subtitle") or "Security & Performance Overview"),
            notes=str(cover_raw.get("notes") or ""),
            prepared_for=str(cover_raw.get("prepared_for") or ""),
            classification=str(cover_raw.get("classification") or ""),
            date_format=str(cover_raw.get("date_format") or "%d/%b/%Y"),
        )
        return cls(
            api_token=str(data.get("api_token") or ""),
            cache_dir=str(data.get("cache_dir") or "~/.cache/cf-report"),
            output_dir=str(data.get("output_dir") or "~/.cf-report"),
            default_zone=str(data.get("default_zone") or ""),
            log_level=str(data.get("log_level") or "info"),
            pdf_image_quality=pdf_image_quality,
            zones=zones,
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


def template_config() -> AppConfig:
    return AppConfig(
        api_token="cfat_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
        cache_dir="~/.cache/cf-report",
        output_dir="~/.cf-report",
        default_zone="",
        log_level="info",
        pdf_image_quality="medium",
        zones=[],
        cover=CoverConfig(),
    )
