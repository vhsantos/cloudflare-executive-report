"""PDF primitive helpers."""

from reportlab.lib.units import inch
from reportlab.platypus import KeepInFrame, Spacer

from cloudflare_executive_report.common.constants import (
    PDF_MAP_SIDE_BY_SIDE_MAP_WIDTH_SHARE,
    PDF_RANKED_BAR_COLUMN_MAX_SHARE,
)
from cloudflare_executive_report.pdf.primitives import (
    _ranked_column_ratios_with_capped_bar,
    clear_render_context,
    flex_row,
    get_render_context,
    initialize,
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


def test_render_context_column_inner_width_matches_theme_helpers() -> None:
    initialize(DEFAULT_THEME)
    try:
        ctx = get_render_context()
        assert abs(ctx.column_inner_width_in(1) - ctx.content_width_in) < 1e-9
        assert abs(ctx.column_inner_width_in(2) - DEFAULT_THEME.half_inner_width_in()) < 1e-9
        assert abs(ctx.column_inner_width_in(3) - DEFAULT_THEME.third_inner_width_in()) < 1e-9
    finally:
        clear_render_context()


def test_flex_row_column_widths_sum_to_content_width() -> None:
    initialize(DEFAULT_THEME)
    try:
        ctx = get_render_context()
        expected_pt = ctx.content_width_in * inch
        sample_rows = [["label", "1", 0.5]]
        ratios = (0.33, 0.33, 0.34)
        for n_tables in (1, 2, 3):
            tables = [("Title", sample_rows, ratios)] * n_tables
            row_table = flex_row(tables)
            total_pt = sum(row_table._colWidths)
            assert abs(total_pt - expected_pt) < 0.02, (n_tables, total_pt, expected_pt)
    finally:
        clear_render_context()


def test_flex_row_rejects_invalid_table_count() -> None:
    initialize(DEFAULT_THEME)
    try:
        sample_rows = [["x", "1", 0.5]]
        ratios = (0.33, 0.33, 0.34)
        one = [("T", sample_rows, ratios)]
        try:
            flex_row([])
            raise AssertionError("expected ValueError")
        except ValueError:
            pass
        try:
            flex_row(one * 4)
            raise AssertionError("expected ValueError")
        except ValueError:
            pass
    finally:
        clear_render_context()
