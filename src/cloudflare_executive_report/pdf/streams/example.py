"""Skeleton PDF stream page - copy this when adding a new stream.

Replace every occurrence of ``example`` / ``Example`` with your stream name,
then fill in the real KPI values, chart calls, and table rows.

DO NOT ship this file as-is; it is a reference template only.
Delete it once you have created your real stream page.
"""

from __future__ import annotations

from typing import Any

from reportlab.platypus import Spacer

from cloudflare_executive_report.common.constants import (
    PDF_SPACE_MEDIUM_PT,
    PDF_SPACE_SMALL_PT,
)
from cloudflare_executive_report.pdf.primitives import (
    flex_row,
    get_render_context,
    kpi_row,
    ranked_rows_from_dicts,
)
from cloudflare_executive_report.pdf.stream_fragments import (
    append_missing_dates_note,
    append_stream_header,
)
from cloudflare_executive_report.pdf.theme import Theme


def collect_example_appendix_notes(
    example: dict[str, Any],
    *,
    profile: str,
) -> list[str]:
    """Return appendix notes for the report appendix page.

    Add a note whenever readers need context to interpret the numbers
    correctly - e.g. sampling caveats, retention limits, or counting
    methodology differences versus the Cloudflare dashboard.

    Return an empty list if there is nothing to add for this profile.
    Strings are de-duplicated across zones before printing.
    """
    notes: list[str] = []
    if profile not in {"executive", "detailed"}:
        return notes
    # Example: add a note that explains how the metric is counted.
    # notes.append(
    #     "Example counts reflect completed requests only; "
    #     "requests that timed out at the edge are excluded."
    # )
    return notes


def append_example_stream(
    story: list[Any],
    *,
    zone_name: str,
    period_start: str,
    period_end: str,
    example: dict[str, Any],
    missing_dates: list[str],
    theme: Theme,
    top: int,
) -> None:
    """Append the Example analytics section to the PDF story.

    Follows the same structure as ``append_cache_stream`` and
    ``append_security_stream``:
    1. Section header (stream title + zone + period).
    2. Missing-dates note (if any days had no data).
    3. KPI row(s).
    4. Timeseries chart (optional).
    5. Ranked tables (optional).

    Parameters
    ----------
    story:
        ReportLab flowables list to append to.
    zone_name:
        Human-readable zone name shown in the header.
    period_start:
        ISO date string ``YYYY-MM-DD`` (inclusive).
    period_end:
        ISO date string ``YYYY-MM-DD`` (inclusive).
    example:
        Aggregated rollup dict from ``build_example_section``.
    missing_dates:
        Dates with no cached data - shown as a warning note.
    theme:
        Active PDF theme (colors, fonts, DPI).
    top:
        Maximum number of rows in ranked tables.
    """
    styles = get_render_context().styles

    # ------------------------------------------------------------------
    # 1. Section header
    # ------------------------------------------------------------------
    # Streams without a layout spec pass an empty set so every block is
    # rendered unconditionally.  To make sections optional (e.g. hide the
    # timeseries for minimal reports), add a layout dataclass to
    # ``pdf/layout_spec.py``, pass it as a parameter here, and replace
    # ``set()`` with ``set(layout.blocks)``.
    append_stream_header(
        story,
        styles,
        theme,
        blocks=set(),
        stream_title="Example",
        zone_name=zone_name,
        period_start=period_start,
        period_end=period_end,
    )

    # ------------------------------------------------------------------
    # 2. Missing-dates note
    # ------------------------------------------------------------------
    append_missing_dates_note(story, styles, set(), missing_dates)

    # ------------------------------------------------------------------
    # 3. KPI row
    # Replace the placeholder values with real fields from ``example``.
    # ``kpi_row`` accepts a list of (label, value) string pairs.
    # ------------------------------------------------------------------
    total = str(example.get("total_count_human") or "0")
    story.append(
        kpi_row(
            [
                ("Total count", total),
                # Add more KPIs here, e.g.:
                # ("Delivered", str(example.get("delivered_human") or "-")),
                # ("Failed", str(example.get("failed_human") or "-")),
            ]
        )
    )
    story.append(Spacer(1, PDF_SPACE_MEDIUM_PT))

    # ------------------------------------------------------------------
    # 4. Timeseries chart (optional)
    # Uncomment and adapt when the stream has daily chart data.
    # ------------------------------------------------------------------
    # from cloudflare_executive_report.pdf.charts import prepare_dual_line_daily_series
    # from cloudflare_executive_report.pdf.stream_fragments import append_prepared_timeseries_chart
    #
    # chart_bytes, sub_title = prepare_dual_line_daily_series(
    #     daily_example_pair,
    #     theme,
    #     chart_title="Example requests",
    #     legend_a="Series A",
    #     legend_b="Series B",
    # )
    # append_prepared_timeseries_chart(story, styles, theme, set(), chart_bytes, sub_title)

    story.append(Spacer(1, PDF_SPACE_SMALL_PT))

    # ------------------------------------------------------------------
    # 5. Ranked table (optional)
    # ``ranked_rows_from_dicts`` turns a list[dict] from the rollup into
    # [[rank_str, label, count_str, pct_str]] rows for ``flex_row``.
    # ------------------------------------------------------------------
    top_rows = ranked_rows_from_dicts(
        list(example.get("top_dimensions") or []),
        top,
        "value",  # key used as the label column
    )
    if top_rows:
        story.append(
            flex_row(
                [("Top dimensions", top_rows, (0.52, 0.18, 0.30))],
            )
        )
