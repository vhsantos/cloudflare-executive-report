from cloudflare_executive_report.pdf.streams.executive_summary import _report_type_suffix


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
