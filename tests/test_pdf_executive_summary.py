from cloudflare_executive_report.pdf.streams.executive_summary import (
    _format_posture_score_pdf_cell,
    _report_type_suffix,
)


def test_report_type_suffix_fixed_labels():
    assert _report_type_suffix("last_month") == " - Last Month"
    assert _report_type_suffix("this_month") == " - This Month (to date)"
    assert _report_type_suffix("last_week") == " - Last Week"
    assert _report_type_suffix("this_week") == " - This Week (to date)"
    assert _report_type_suffix("yesterday") == " - Yesterday"


def test_report_type_suffix_last_n_dynamic():
    assert _report_type_suffix("last_7") == " - Last 7 Days"
    assert _report_type_suffix("last_30") == " - Last 30 Days"
    assert _report_type_suffix("last_10") == " - Last 10 Days"


def test_report_type_suffix_omits_custom_incremental():
    assert _report_type_suffix("custom") == ""
    assert _report_type_suffix("incremental") == ""
    assert _report_type_suffix("") == ""


def test_format_posture_score_pdf_cell_rounds_and_pairs_grade() -> None:
    assert _format_posture_score_pdf_cell(71.7, "C") == "72 / C"
    assert _format_posture_score_pdf_cell(83.3, "B") == "83 / B"


def test_format_posture_score_pdf_cell_missing_returns_dash() -> None:
    assert _format_posture_score_pdf_cell(None, "C") == "-"
    assert _format_posture_score_pdf_cell(80.0, "") == "-"
    assert _format_posture_score_pdf_cell("not-a-number", "A") == "-"
