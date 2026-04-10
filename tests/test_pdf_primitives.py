"""PDF primitive helpers."""

from reportlab.lib.units import inch
from reportlab.platypus import KeepInFrame, Spacer

from cloudflare_executive_report.common.constants import (
    PDF_MAP_SIDE_BY_SIDE_MAP_WIDTH_SHARE,
    PDF_RANKED_BAR_COLUMN_MAX_SHARE,
)
from cloudflare_executive_report.pdf.primitives import (
    _ranked_column_ratios_with_capped_bar,
    map_side_by_side_table,
    ranked_table_label_cell,
)
from cloudflare_executive_report.pdf.styles import build_styles
from cloudflare_executive_report.pdf.theme import DEFAULT_THEME


def test_ranked_table_label_uses_keep_in_frame_truncate():
    styles = build_styles(DEFAULT_THEME)
    k = ranked_table_label_cell("selector1._domainkey.example.com", styles)
    assert isinstance(k, KeepInFrame)
    assert k.mode == "truncate"


def test_ranked_column_ratios_cap_bar_share():
    a, b, c = _ranked_column_ratios_with_capped_bar(
        (0.18, 0.16, 0.66), PDF_RANKED_BAR_COLUMN_MAX_SHARE
    )
    assert abs(c - PDF_RANKED_BAR_COLUMN_MAX_SHARE) < 1e-9
    assert abs(a + b + c - 1.0) < 1e-9


def test_map_side_by_side_table_column_widths_fill_content_width():
    content_in = 6.0
    left = Spacer(1, 4)
    right = Spacer(1, 4)
    t = map_side_by_side_table(left, right, content_width_in=content_in)
    w0, w1 = t._colWidths
    assert abs((w0 + w1) - content_in * inch) < 0.01
    assert abs(w0 - content_in * inch * PDF_MAP_SIDE_BY_SIDE_MAP_WIDTH_SHARE) < 0.02
