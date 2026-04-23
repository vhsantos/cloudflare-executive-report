"""PDF figure quality preset."""

import pytest

from cloudflare_executive_report.config import AppConfig
from cloudflare_executive_report.pdf.figure_quality import (
    PdfFigureQuality,
    parse_pdf_image_quality,
    theme_with_pdf_image_quality,
)
from cloudflare_executive_report.pdf.theme import DEFAULT_THEME


def test_parse_pdf_image_quality_aliases():
    assert parse_pdf_image_quality("LOW") == PdfFigureQuality.low
    assert parse_pdf_image_quality(None) == PdfFigureQuality.high


def test_parse_pdf_image_quality_invalid():
    with pytest.raises(ValueError, match="pdf_image_quality"):
        parse_pdf_image_quality("ultra")


def test_theme_with_pdf_image_quality_dpis():
    low = theme_with_pdf_image_quality(PdfFigureQuality.low)
    assert low.chart_dpi == 72 and low.map_dpi == 72
    med = theme_with_pdf_image_quality(PdfFigureQuality.medium)
    assert med.chart_dpi == 96 and med.map_dpi == 96
    high = theme_with_pdf_image_quality(PdfFigureQuality.high)
    assert high.chart_dpi == 130 and high.map_dpi == 130


def test_config_from_yaml_validates_figure_quality():
    cfg = AppConfig.from_yaml_dict({"pdf": {"image_quality": "high"}, "zones": []})
    assert cfg.pdf.image_quality == "high"


def test_config_from_yaml_rejects_bad_figure_quality():
    with pytest.raises(ValueError, match="pdf_image_quality"):
        AppConfig.from_yaml_dict({"pdf": {"image_quality": "x"}, "zones": []})


def test_default_theme_matches_medium_preset():
    m = theme_with_pdf_image_quality(PdfFigureQuality.medium)
    assert m.chart_dpi == DEFAULT_THEME.chart_dpi == 96
    assert m.map_dpi == DEFAULT_THEME.map_dpi == 96
