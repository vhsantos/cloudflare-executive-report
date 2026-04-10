"""Reusable ReportLab flowables."""

from __future__ import annotations

import io
from typing import Any
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import Flowable, Image, KeepInFrame, Paragraph, Table, TableStyle

from cloudflare_executive_report.common.constants import (
    PDF_MAP_SIDE_BY_SIDE_MAP_WIDTH_SHARE,
    PDF_RANKED_BAR_COLUMN_MAX_SHARE,
    PDF_RANKED_BAR_TRACK_HEIGHT_PT,
    PDF_RANKED_TABLE_ROW_PAD_PT,
    PDF_SPACE_MEDIUM_PT,
)
from cloudflare_executive_report.common.formatting import format_count_human
from cloudflare_executive_report.pdf.styles import build_styles
from cloudflare_executive_report.pdf.theme import Theme

# ``KeepInFrame`` maxWidth (pt). ``wrap()`` uses ``min(this, cell_availWidth)``; a huge
# value means the table cell's inner width (after padding) is always the effective cap,
# so we do not duplicate column-width math here.
_KEEP_IN_FRAME_MAX_WIDTH_PT = 1e9

# Max height (pt) for the ranked name-column clip box. ``KeepInFrame.wrap`` uses
# ``min(maxHeight, availHeight)``; with ``mode="truncate"``, drawing outside that
# rectangle is clipped so labels do not overlap the count/bar columns. ~11pt matches
# one line at ``RepRankedLabel`` (9pt / 11 leading); raise if two lines should show.
_RANKED_LABEL_LINE_PT = 11.0


def ranked_table_label_cell(text: str, styles: Any) -> KeepInFrame:
    """Clip a ranked-table label to its cell (``Table`` has no overflow flag).

    Wraps a ``Paragraph`` in ``KeepInFrame(..., mode="truncate")``. ReportLab clips
    drawing to a rectangle so long names (e.g. DNS qnames) do not spill into sibling
    columns.

    ``KeepInFrame(maxWidth, maxHeight, ...)`` are caps; ``wrap()`` intersects them with
    the parent cell's ``availWidth`` / ``availHeight``:

    * ``maxWidth`` - ``_KEEP_IN_FRAME_MAX_WIDTH_PT`` (``1e9``) so ``min(maxWidth,
      availWidth)`` is always the cell inner width; avoids duplicating column math.
    * ``maxHeight`` - ``_RANKED_LABEL_LINE_PT``; extra vertical content is clipped.

    Args:
        text: Label string; ``&``, ``<``, ``>`` escaped for ReportLab markup.
        styles: From ``build_styles``; must define ``RepRankedLabel``.

    Returns:
        Flowable for column 0 of ``table_with_bars`` / ``colo_table_wrap``.
    """
    para = Paragraph(escape(str(text).strip()), styles["RepRankedLabel"])
    return KeepInFrame(
        _KEEP_IN_FRAME_MAX_WIDTH_PT,
        _RANKED_LABEL_LINE_PT,
        [para],
        mode="truncate",
        hAlign="LEFT",
    )


class KpiColumnDivider(Flowable):
    """Thin vertical rule spanning ``span_frac`` of the cell height (centered)."""

    def __init__(
        self,
        *,
        line_color: Any,
        width_pt: float = 1.25,
        span_frac: float = 0.8,
        line_width: float = 0.5,
    ) -> None:
        super().__init__()
        self.line_color = line_color
        self.width_pt = width_pt
        self.span_frac = span_frac
        self.line_width = line_width
        self._h = 48.0

    def wrap(self, availWidth: float, availHeight: float | None = None) -> tuple[float, float]:
        ah = float(availHeight) if availHeight else 0.0
        if ah <= 0.0 or ah > 800.0:
            ah = 52.0
        self._h = max(ah, 36.0)
        return (self.width_pt, self._h)

    def draw(self) -> None:
        h = self._h
        margin = h * (1.0 - self.span_frac) / 2.0
        y0, y1 = margin, h - margin
        self.canv.saveState()
        self.canv.setStrokeColor(self.line_color)
        self.canv.setLineWidth(self.line_width)
        mid = self.width_pt / 2.0
        self.canv.line(mid, y0, mid, y1)
        self.canv.restoreState()


def section_title(text: str, styles: Any, theme: Theme) -> Paragraph:
    return Paragraph(
        f"<font color='{theme.slate}'>{text}</font>",
        styles["RepSection"],
    )


def figure_from_bytes(png: bytes, *, width_in: float, height_in: float) -> Image:
    return Image(io.BytesIO(png), width=width_in * inch, height=height_in * inch)


def map_side_by_side_table(
    map_flowable: Flowable,
    side_table_flowable: Flowable,
    *,
    content_width_in: float,
) -> Table:
    """Lay out map and ranked table in one row (two thirds / one third of content width).

    Args:
        map_flowable: Left cell (typically the world map image).
        side_table_flowable: Right cell (typically ``colo_table_wrap`` or ``table_with_bars``).
        content_width_in: Full content width in inches; column widths sum to this width.
    """
    w_total_pt = content_width_in * inch
    w_map_pt = w_total_pt * PDF_MAP_SIDE_BY_SIDE_MAP_WIDTH_SHARE
    w_table_pt = w_total_pt - w_map_pt
    side_gutter_pt = PDF_SPACE_MEDIUM_PT
    outer = Table([[map_flowable, side_table_flowable]], colWidths=[w_map_pt, w_table_pt])
    outer.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (0, 0), 0),
                ("LEFTPADDING", (1, 0), (1, 0), side_gutter_pt),
                ("RIGHTPADDING", (1, 0), (1, 0), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    return outer


def two_column_gap_style(theme: Theme) -> TableStyle:
    gap_pt = theme.col_gap_in * inch
    half = gap_pt / 2
    return TableStyle(
        [
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (0, 0), 0),
            ("RIGHTPADDING", (0, 0), (0, 0), half),
            ("LEFTPADDING", (0, 1), (0, 1), half),
            ("RIGHTPADDING", (0, 1), (0, 1), 0),
        ]
    )


def ranked_rows_from_dicts(
    items: list[dict[str, Any]],
    top: int,
    label_key: str,
    *,
    value_key: str = "count",
    pct_key: str = "percentage",
) -> list[list[Any]]:
    rows: list[list[Any]] = []
    for item in items[:top]:
        label = str(item.get(label_key, ""))
        cnt = int(item.get(value_key, 0))
        pct = float(item.get(pct_key, 0.0))
        bar_w = min(1.0, max(0.0, pct / 100.0))
        rows.append([label, format_count_human(cnt), bar_w])
    return rows


def _inner_grid_width_pt(total_width_in: float, theme: Theme) -> float:
    return max(0.0, total_width_in * inch - 2 * theme.outer_card_pad_pt)


def _scale_ratios_to_pt(total_pt: float, ratios: tuple[float, ...]) -> list[float]:
    s = sum(ratios)
    col_pt = [total_pt * (x / s) for x in ratios]
    drift = total_pt - sum(col_pt)
    if col_pt:
        col_pt[-1] += drift
    return col_pt


def _ranked_column_ratios_with_capped_bar(
    ratios: tuple[float, float, float],
    max_bar_share: float,
) -> tuple[float, float, float]:
    """Normalize (label, count, bar) ratios so the bar column is at most ``max_bar_share``."""
    a, b, c = ratios
    s = a + b + c
    if s <= 0:
        return ratios
    a, b, c = a / s, b / s, c / s
    if c <= max_bar_share:
        return (a, b, c)
    freed = c - max_bar_share
    ab = a + b
    if ab <= 1e-12:
        return (0.0, 0.0, 1.0)
    return (a + freed * (a / ab), b + freed * (b / ab), max_bar_share)


def _bar_cell_table(bar_total_pt: float, bar_w: float, theme: Theme) -> Table:
    total = max(bar_total_pt, 1.0)
    bw = min(1.0, max(0.0, bar_w))
    w1 = total * bw
    w2 = total - w1
    min_vis = min(1.0, total * 0.015)
    if w1 > 0 and w1 < min_vis and w2 > min_vis:
        w1 = min(min_vis, total * 0.35)
        w2 = total - w1
    bar_h = PDF_RANKED_BAR_TRACK_HEIGHT_PT
    t = Table([["", ""]], colWidths=[w1, w2], rowHeights=[bar_h])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, 0), colors.HexColor(theme.primary)),
                ("BACKGROUND", (1, 0), (1, 0), colors.HexColor(theme.bar_track)),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    return t


def _ranked_inner_table_style(num_rows: int, theme: Theme) -> list:
    if num_rows <= 0:
        return []
    last = num_rows - 1
    vpad = PDF_RANKED_TABLE_ROW_PAD_PT
    styles: list[tuple] = [
        ("FONT", (1, 0), (1, last), "Helvetica", 9),
        ("TEXTCOLOR", (0, 0), (-1, last), colors.HexColor(theme.slate)),
        ("ALIGN", (0, 0), (0, last), "LEFT"),
        ("ALIGN", (1, 0), (1, last), "RIGHT"),
        ("VALIGN", (0, 0), (-1, last), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, colors.HexColor(theme.row_alt)]),
        ("TOPPADDING", (0, 0), (-1, last), vpad),
        ("BOTTOMPADDING", (0, 0), (-1, last), vpad),
        ("LEFTPADDING", (0, 0), (1, last), 8),
        ("RIGHTPADDING", (0, 0), (1, last), 6),
        ("LEFTPADDING", (2, 0), (2, last), 0),
        ("RIGHTPADDING", (2, 0), (2, last), 0),
    ]
    for r in range(num_rows - 1):
        styles.append(("LINEBELOW", (0, r), (-1, r), 0.25, colors.HexColor(theme.border)))
    return styles


def table_with_bars(
    title: str,
    rows: list[list[Any]],
    styles: Any,
    *,
    ratios: tuple[float, float, float],
    total_width_in: float,
    theme: Theme,
    show_outer_card: bool = True,
) -> Table:
    inner_w_pt = _inner_grid_width_pt(total_width_in, theme)
    ratios_capped = _ranked_column_ratios_with_capped_bar(ratios, PDF_RANKED_BAR_COLUMN_MAX_SHARE)
    col_pt = _scale_ratios_to_pt(inner_w_pt, ratios_capped)
    bar_total_pt = col_pt[2]
    data_rows: list[list[Any]] = []
    for label, cnt_s, bar_w in rows:
        bar_cell = _bar_cell_table(bar_total_pt, bar_w, theme)
        data_rows.append([ranked_table_label_cell(str(label), styles), cnt_s, bar_cell])
    inner = Table(data_rows, colWidths=col_pt)
    inner.setStyle(TableStyle(_ranked_inner_table_style(len(data_rows), theme)))
    title_p = Paragraph(f"<font color='{theme.slate}'>{title}</font>", styles["RepCardTitle"])
    pad = theme.outer_card_pad_pt
    outer = Table([[title_p], [inner]], colWidths=[total_width_in * inch])
    if show_outer_card:
        outer.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(theme.card_bg)),
                    ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor(theme.border)),
                    ("TOPPADDING", (0, 0), (0, 0), pad),
                    ("BOTTOMPADDING", (0, 0), (0, 0), 0),
                    ("LEFTPADDING", (0, 0), (0, 0), pad),
                    ("RIGHTPADDING", (0, 0), (0, 0), pad),
                    ("TOPPADDING", (0, 1), (0, 1), 0),
                    ("BOTTOMPADDING", (0, 1), (0, 1), pad),
                    ("LEFTPADDING", (0, 1), (0, 1), pad),
                    ("RIGHTPADDING", (0, 1), (0, 1), pad),
                ]
            )
        )
    else:
        outer.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (0, 0), 0),
                    ("BOTTOMPADDING", (0, 0), (0, 0), 4),
                    ("LEFTPADDING", (0, 0), (0, 0), 0),
                    ("RIGHTPADDING", (0, 0), (0, 0), 0),
                    ("TOPPADDING", (0, 1), (0, 1), 0),
                    ("BOTTOMPADDING", (0, 1), (0, 1), 0),
                    ("LEFTPADDING", (0, 1), (0, 1), 0),
                    ("RIGHTPADDING", (0, 1), (0, 1), 0),
                ]
            )
        )
    return outer


def colo_table_wrap(
    colo_rows: list[list[Any]],
    *,
    total_width_in: float,
    theme: Theme,
    styles: Any,
) -> Table:
    inner_w_pt = _inner_grid_width_pt(total_width_in, theme)
    ratios = (0.28, 0.26, 0.46)
    ratios_capped = _ranked_column_ratios_with_capped_bar(ratios, PDF_RANKED_BAR_COLUMN_MAX_SHARE)
    col_pt = _scale_ratios_to_pt(inner_w_pt, ratios_capped)
    bar_total_pt = col_pt[2]
    data_rows: list[list[Any]] = []
    for label, cnt_s, bar_w in colo_rows:
        bar_cell = _bar_cell_table(bar_total_pt, bar_w, theme)
        data_rows.append([ranked_table_label_cell(str(label), styles), cnt_s, bar_cell])
    t = Table(data_rows, colWidths=col_pt)
    t.setStyle(TableStyle(_ranked_inner_table_style(len(data_rows), theme)))
    wrap = Table([[t]], colWidths=[total_width_in * inch])
    wrap.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(theme.card_bg)),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor(theme.border)),
                ("TOPPADDING", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                ("LEFTPADDING", (0, 0), (-1, -1), theme.outer_card_pad_pt),
                ("RIGHTPADDING", (0, 0), (-1, -1), theme.outer_card_pad_pt),
            ]
        )
    )
    return wrap


def kpi_multi_cell_row(
    cells: list[tuple[str, str] | tuple[str, str, str]],
    styles: Any,
    *,
    theme: Theme,
    content_width_in: float,
) -> Table:
    """KPI band: N columns, short vertical dividers, centered text, tighter padding."""
    if not cells:
        raise ValueError("kpi_multi_cell_row requires at least one cell")
    w_full = content_width_in * inch
    n = len(cells)
    sep_w = 1.5
    gap_total = max(0, n - 1) * sep_w
    cell_w = (w_full - gap_total) / n
    div_color = colors.HexColor(theme.border)

    def _indicator_color(indicator_text: str) -> str:
        if indicator_text.startswith("G:"):
            return "#00AA00"
        if indicator_text.startswith("R:"):
            return "#CC0000"
        if indicator_text.startswith("N:"):
            return theme.muted
        if indicator_text.startswith("▲"):
            return "#00AA00"
        if indicator_text.startswith("▼"):
            return "#CC0000"
        return theme.muted

    row: list[Any] = []
    col_widths: list[float] = []
    for i, cell in enumerate(cells):
        label = cell[0]
        value = cell[1]
        indicator = cell[2] if len(cell) > 2 else ""
        if i > 0:
            row.append(
                KpiColumnDivider(
                    line_color=div_color,
                    width_pt=sep_w,
                    span_frac=0.8,
                )
            )
            col_widths.append(sep_w)
        value_text = escape(str(value))
        raw_indicator = str(indicator).strip()
        indicator_color = _indicator_color(raw_indicator)
        if raw_indicator.startswith(("G:", "R:", "N:")):
            raw_indicator = raw_indicator[2:]
        indicator_text = escape(raw_indicator)
        value_block: Any
        if indicator_text:
            raw_value = str(value)
            raw_indicator = str(indicator).strip()
            value_w = max(1.0, stringWidth(raw_value, "Helvetica-Bold", 20))
            indicator_w = max(1.0, stringWidth(raw_indicator, "Helvetica-Bold", 7))
            value_line = Table(
                [
                    [
                        Paragraph(value_text, styles["RepKpiValue"]),
                        Paragraph(
                            (
                                f"<font size='7' color='{indicator_color}'>"
                                f"<b>{indicator_text}</b></font>"
                            ),
                            styles["RepKpiLabelCenter"],
                        ),
                    ]
                ],
                colWidths=[value_w, indicator_w],
            )
            value_line.setStyle(
                TableStyle(
                    [
                        ("ALIGN", (0, 0), (0, 0), "LEFT"),
                        ("ALIGN", (1, 0), (1, 0), "LEFT"),
                        ("VALIGN", (0, 0), (1, 0), "MIDDLE"),
                        ("LEFTPADDING", (0, 0), (1, 0), 0),
                        ("RIGHTPADDING", (0, 0), (1, 0), 0),
                        ("TOPPADDING", (0, 0), (1, 0), 0),
                        ("BOTTOMPADDING", (0, 0), (1, 0), 0),
                    ]
                )
            )
            value_block = Table([[value_line]], colWidths=[cell_w])
            value_block.setStyle(
                TableStyle(
                    [
                        ("ALIGN", (0, 0), (0, 0), "CENTER"),
                        ("VALIGN", (0, 0), (0, 0), "MIDDLE"),
                        ("LEFTPADDING", (0, 0), (0, 0), 0),
                        ("RIGHTPADDING", (0, 0), (0, 0), 0),
                        ("TOPPADDING", (0, 0), (0, 0), 0),
                        ("BOTTOMPADDING", (0, 0), (0, 0), 0),
                    ]
                )
            )
        else:
            value_block = Paragraph(value_text, styles["RepKpiValueCenter"])
        inner = Table(
            [
                [Paragraph(escape(str(label)), styles["RepKpiLabelCenter"])],
                [value_block],
            ],
            colWidths=[cell_w],
        )
        inner.setStyle(
            TableStyle(
                [
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 2),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ]
            )
        )
        row.append(inner)
        col_widths.append(cell_w)

    summary = Table([row], colWidths=col_widths)
    style_cmds: list[tuple[Any, ...]] = [
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(theme.row_alt)),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor(theme.border)),
        ("LINEBELOW", (0, 0), (-1, -1), 1.5, colors.HexColor(theme.primary)),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
    ]
    for c in range(1, len(col_widths), 2):
        style_cmds.extend(
            [
                ("LEFTPADDING", (c, 0), (c, 0), 0),
                ("RIGHTPADDING", (c, 0), (c, 0), 0),
                ("TOPPADDING", (c, 0), (c, 0), 0),
                ("BOTTOMPADDING", (c, 0), (c, 0), 0),
            ]
        )
    summary.setStyle(TableStyle(style_cmds))
    return summary


def kpi_two_cell_row(
    left_label: str,
    left_value: str,
    right_label: str,
    right_value: str,
    styles: Any,
    *,
    theme: Theme,
    content_width_in: float,
) -> Table:
    return kpi_multi_cell_row(
        [(left_label, left_value), (right_label, right_value)],
        styles,
        theme=theme,
        content_width_in=content_width_in,
    )


def make_styles(theme: Theme) -> Any:
    return build_styles(theme)
