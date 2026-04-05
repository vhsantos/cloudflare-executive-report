"""PDF primitive helpers."""

from reportlab.platypus import KeepInFrame

from cloudflare_executive_report.pdf.primitives import ranked_table_label_cell
from cloudflare_executive_report.pdf.styles import build_styles
from cloudflare_executive_report.pdf.theme import DEFAULT_THEME


def test_ranked_table_label_uses_keep_in_frame_truncate():
    styles = build_styles(DEFAULT_THEME)
    k = ranked_table_label_cell("selector1._domainkey.example.com", styles)
    assert isinstance(k, KeepInFrame)
    assert k.mode == "truncate"
