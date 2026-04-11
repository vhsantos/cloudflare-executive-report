"""Tests for shared PDF stream helpers."""

from __future__ import annotations

import cloudflare_executive_report.pdf.stream_fragments as stream_fragments
from cloudflare_executive_report.pdf.theme import DEFAULT_THEME


def test_append_prepared_timeseries_chart_delegates_with_heading_none(
    monkeypatch,
) -> None:
    """append_prepared_timeseries_chart forwards to append_chart_section with heading None."""
    calls: list[dict[str, object]] = []

    def fake_append_chart_section(*args: object, **kwargs: object) -> None:
        calls.append({"args": args, "kwargs": kwargs})

    monkeypatch.setattr(stream_fragments, "append_chart_section", fake_append_chart_section)

    story: list = []
    stream_fragments.append_prepared_timeseries_chart(
        story,
        {},
        DEFAULT_THEME,
        {"timeseries"},
        b"x",
        "granularity note",
    )
    assert len(calls) == 1
    kw = calls[0]["kwargs"]
    assert kw["heading"] is None
    assert kw["chart_bytes"] == b"x"
    assert kw["subtitle"] == "granularity note"


def test_append_prepared_timeseries_chart_default_subtitle_empty(monkeypatch) -> None:
    """Omitted subtitle becomes empty string on the delegated call."""
    calls: list[dict[str, object]] = []

    def fake_append_chart_section(*args: object, **kwargs: object) -> None:
        calls.append({"kwargs": kwargs})

    monkeypatch.setattr(stream_fragments, "append_chart_section", fake_append_chart_section)

    stream_fragments.append_prepared_timeseries_chart(
        [],
        {},
        DEFAULT_THEME,
        {"timeseries"},
        b"y",
    )
    assert calls[0]["kwargs"]["subtitle"] == ""
