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
class AppConfig:
    api_token: str = ""
    cache_dir: str = "~/.cache/cf-report"
    default_zone: str = ""
    log_level: str = "info"
    # low | medium | high - matplotlib DPI for PDF maps/charts (smaller file vs sharper plots)
    pdf_image_quality: str = "medium"
    zones: list[ZoneEntry] = field(default_factory=list)

    def cache_path(self) -> Path:
        return expand_path(self.cache_dir)

    def to_yaml_dict(self) -> dict[str, Any]:
        return {
            "api_token": self.api_token,
            "cache_dir": self.cache_dir,
            "default_zone": self.default_zone,
            "log_level": self.log_level,
            "pdf_image_quality": self.pdf_image_quality,
            "zones": [{"id": z.id, "name": z.name} for z in self.zones],
        }

    @classmethod
    def from_yaml_dict(cls, data: dict[str, Any]) -> AppConfig:
        zones_raw = data.get("zones") or []
        zones = [ZoneEntry(id=str(z["id"]), name=str(z["name"])) for z in zones_raw]
        pq_raw = data.get("pdf_image_quality")
        pdf_image_quality = parse_pdf_image_quality(
            str(pq_raw) if pq_raw is not None else None
        ).value
        return cls(
            api_token=str(data.get("api_token") or ""),
            cache_dir=str(data.get("cache_dir") or "~/.cache/cf-report"),
            default_zone=str(data.get("default_zone") or ""),
            log_level=str(data.get("log_level") or "info"),
            pdf_image_quality=pdf_image_quality,
            zones=zones,
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
        default_zone="",
        log_level="info",
        pdf_image_quality="medium",
        zones=[],
    )
