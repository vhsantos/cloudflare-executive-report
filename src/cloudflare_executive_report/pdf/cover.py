"""Report-level cover page for PDF output."""

from __future__ import annotations

from datetime import UTC, datetime
from html import escape
from typing import Any

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import inch
from reportlab.platypus import Image, PageBreak, Paragraph, Spacer

from cloudflare_executive_report.config import CoverConfig
from cloudflare_executive_report.pdf.layout_spec import ReportSpec
from cloudflare_executive_report.pdf.theme import Theme


def _logo_flowable(cover: CoverConfig) -> Image | None:
    p = cover.resolved_logo_path()
    if p is None:
        return None
    try:
        if not p.is_file():
            return None
        return Image(str(p), width=3.2 * inch, height=1.2 * inch, hAlign="CENTER")
    except Exception:
        return None


def _safe_lines(text: str) -> list[str]:
    raw = text.strip()
    if not raw:
        return []
    return [ln.strip() for ln in raw.splitlines() if ln.strip()]


def _format_cover_date(cover: CoverConfig, now_utc: datetime) -> str:
    fmt = cover.date_format.strip() or "%d/%b/%Y"
    try:
        return now_utc.strftime(fmt)
    except Exception:
        return now_utc.strftime("%d/%b/%Y")


def _measure_flowable(flowable: Any, width_pt: float) -> float:
    if isinstance(flowable, Spacer):
        return float(getattr(flowable, "height", 0.0))
    if isinstance(flowable, Image):
        return float(getattr(flowable, "drawHeight", 0.0))
    if hasattr(flowable, "wrap"):
        _, h = flowable.wrap(width_pt, 10_000)
        return float(h)
    return 0.0


def _measure_block(flowables: list[Any], width_pt: float) -> float:
    return sum(_measure_flowable(f, width_pt) for f in flowables)


def _build_notes_block(notes: list[str], styles: Any, theme: Theme) -> list[Any]:
    if not notes:
        return []
    block: list[Any] = [
        Paragraph(
            f"<font color='{theme.slate}'><b>Notes:</b></font>",
            styles["RepSectionTight"],
        )
    ]
    for ln in notes:
        block.append(
            Paragraph(
                f"<font color='{theme.muted}'>- {escape(ln)}</font>",
                styles["RepFootnote"],
            )
        )
    return block


def append_cover_page(
    story: list[Any],
    *,
    cover: CoverConfig,
    spec: ReportSpec,
    styles: Any,
    theme: Theme,
) -> bool:
    """Append one report-level cover page. Returns True when appended."""
    if not cover.enabled:
        return False

    logo = _logo_flowable(cover)
    now_utc = datetime.now(UTC)
    generated = _format_cover_date(cover, now_utc)

    content_width_pt = A4[0] - 2 * theme.margin_in * inch
    usable_height_pt = A4[1] - (theme.top_margin_in + theme.bottom_margin_in) * inch

    top_block: list[Any] = []
    if logo is not None:
        top_block.append(logo)
    if cover.company_name.strip():
        if top_block:
            top_block.append(Spacer(1, 8))
        top_block.append(
            Paragraph(
                (
                    f"<para align='center'><font color='{theme.slate}' size='16'>"
                    f"<b>{escape(cover.company_name.strip())}</b></font></para>"
                ),
                styles["RepSubtitle"],
            )
        )

    middle_block: list[Any] = [
        Paragraph(
            (
                f"<para align='center' leading='24'><font color='{theme.slate}' size='24'>"
                f"<b>{escape(cover.title.strip() or 'Cloudflare Executive Report')}</b>"
                "</font></para>"
            ),
            styles["RepH1"],
        ),
        Spacer(1, 6),
        Paragraph(
            (
                f"<para align='center' leading='13'><font color='{theme.muted}' size='13'>"
                f"{escape(cover.subtitle.strip() or 'Security & Performance Overview')}"
                "</font></para>"
            ),
            styles["RepSubtitle"],
        ),
    ]

    if cover.prepared_for.strip():
        middle_block.append(Spacer(1, 96))
        middle_block.append(
            Paragraph(
                (
                    "<para align='center' leading='12'>"
                    f"<font color='{theme.slate}' size='11'>Prepared for: "
                    f"<b>{escape(cover.prepared_for.strip())}</b></font></para>"
                ),
                styles["RepSubtitle"],
            )
        )
        middle_block.append(Spacer(1, 24))

    middle_block.extend(
        [
            Paragraph(
                (
                    "<para align='center' leading='6'>"
                    f"<font color='{theme.slate}' size='11'>Date: <b>{escape(generated)}</b>"
                    "</font></para>"
                ),
                styles["RepSubtitle"],
            ),
            Paragraph(
                (
                    "<para align='center' leading='6'>"
                    f"<font color='{theme.slate}' size='11'>Period: "
                    f"<b>{escape(spec.start)} to {escape(spec.end)} (UTC)</b></font></para>"
                ),
                styles["RepSubtitle"],
            ),
        ]
    )

    if cover.classification.strip():
        middle_block.append(
            Paragraph(
                (
                    "<para align='center' leading='6'>"
                    f"<font color='{theme.muted}' size='11'>"
                    f"{escape(cover.classification.strip())}</font></para>"
                ),
                styles["RepSubtitle"],
            )
        )

    notes_lines = _safe_lines(cover.notes)
    notes_block = _build_notes_block(notes_lines, styles, theme)

    # Keep top close to top margin, then distribute the rest across
    # TOP->MIDDLE, MIDDLE->BOTTOM, and BOTTOM->end.
    top_gap_pt = 64.0
    min_gap_pt = 14.0
    safety_margin_pt = 8.0
    top_h = _measure_block(top_block, content_width_pt)
    middle_h = _measure_block(middle_block, content_width_pt)
    notes_h = _measure_block(notes_block, content_width_pt)
    while (
        notes_lines
        and (top_h + middle_h + notes_h + top_gap_pt + min_gap_pt * 3 + safety_margin_pt)
        > usable_height_pt
    ):
        notes_lines = notes_lines[:-1]
        notes_block = _build_notes_block(notes_lines, styles, theme)
        notes_h = _measure_block(notes_block, content_width_pt)

    total_h = top_h + middle_h + notes_h
    if total_h + top_gap_pt + min_gap_pt * 3 + safety_margin_pt <= usable_height_pt:
        between_pt = (usable_height_pt - total_h - top_gap_pt - safety_margin_pt) / 3.0
    else:
        between_pt = min_gap_pt

    story.append(Spacer(1, top_gap_pt))
    story.extend(top_block)
    story.append(Spacer(1, between_pt))
    story.extend(middle_block)
    story.append(Spacer(1, between_pt))
    story.extend(notes_block)

    story.append(PageBreak())
    return True
