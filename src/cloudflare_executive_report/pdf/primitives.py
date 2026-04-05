"""Reusable ReportLab flowables."""

from __future__ import annotations

import io
from typing import Any

from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import Image, Paragraph, Table, TableStyle

from cloudflare_executive_report.aggregate import format_count_human
from cloudflare_executive_report.pdf.styles import build_styles
from cloudflare_executive_report.pdf.theme import Theme


def section_title(text: str, styles: Any, theme: Theme) -> Paragraph:
    return Paragraph(
        f"<font color='{theme.slate}'>{text}</font>",
        styles["RepSection"],
    )


def figure_from_bytes(png: bytes, *, width_in: float, height_in: float) -> Image:
    return Image(io.BytesIO(png), width=width_in * inch, height=height_in * inch)


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


def _bar_cell_table(bar_total_pt: float, bar_w: float, theme: Theme) -> Table:
    total = max(bar_total_pt, 1.0)
    bw = min(1.0, max(0.0, bar_w))
    w1 = total * bw
    w2 = total - w1
    min_vis = min(2.0, total * 0.03)
    if w1 > 0 and w1 < min_vis and w2 > min_vis:
        w1 = min(min_vis, total * 0.5)
        w2 = total - w1
    t = Table([["", ""]], colWidths=[w1, w2], rowHeights=[9])
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
    styles: list[tuple] = [
        ("FONT", (0, 0), (0, last), "Helvetica", 9),
        ("FONT", (1, 0), (1, last), "Helvetica", 9),
        ("TEXTCOLOR", (0, 0), (-1, last), colors.HexColor(theme.slate)),
        ("ALIGN", (0, 0), (0, last), "LEFT"),
        ("ALIGN", (1, 0), (1, last), "RIGHT"),
        ("VALIGN", (0, 0), (-1, last), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, colors.HexColor(theme.row_alt)]),
        ("TOPPADDING", (0, 0), (-1, last), 5),
        ("BOTTOMPADDING", (0, 0), (-1, last), 5),
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
) -> Table:
    inner_w_pt = _inner_grid_width_pt(total_width_in, theme)
    col_pt = _scale_ratios_to_pt(inner_w_pt, ratios)
    bar_total_pt = col_pt[2]
    data_rows: list[list[Any]] = []
    for label, cnt_s, bar_w in rows:
        data_rows.append([label, cnt_s, _bar_cell_table(bar_total_pt, bar_w, theme)])
    inner = Table(data_rows, colWidths=col_pt)
    inner.setStyle(TableStyle(_ranked_inner_table_style(len(data_rows), theme)))
    title_p = Paragraph(f"<font color='{theme.slate}'>{title}</font>", styles["RepCardTitle"])
    pad = theme.outer_card_pad_pt
    outer = Table([[title_p], [inner]], colWidths=[total_width_in * inch])
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
    return outer


def colo_table_wrap(
    colo_rows: list[list[Any]],
    *,
    total_width_in: float,
    theme: Theme,
) -> Table:
    inner_w_pt = _inner_grid_width_pt(total_width_in, theme)
    ratios = (0.18, 0.16, 0.66)
    col_pt = _scale_ratios_to_pt(inner_w_pt, ratios)
    bar_total_pt = col_pt[2]
    data_rows: list[list[Any]] = []
    for label, cnt_s, bar_w in colo_rows:
        data_rows.append([label, cnt_s, _bar_cell_table(bar_total_pt, bar_w, theme)])
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
    w_full = content_width_in * inch
    left = Table(
        [
            [Paragraph(left_label, styles["RepKpiLabel"])],
            [Paragraph(left_value, styles["RepKpiValue"])],
        ],
        colWidths=[w_full / 2 - 6],
    )
    right = Table(
        [
            [Paragraph(right_label, styles["RepKpiLabel"])],
            [Paragraph(right_value, styles["RepKpiValue"])],
        ],
        colWidths=[w_full / 2 - 6],
    )
    summary = Table([[left, right]], colWidths=[w_full / 2, w_full / 2])
    summary.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(theme.row_alt)),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor(theme.border)),
                ("LINEBELOW", (0, 0), (-1, -1), 1.5, colors.HexColor(theme.primary)),
                ("LEFTPADDING", (0, 0), (-1, -1), 16),
                ("RIGHTPADDING", (0, 0), (-1, -1), 16),
                ("TOPPADDING", (0, 0), (-1, -1), 14),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 16),
            ]
        )
    )
    return summary


def make_styles(theme: Theme) -> Any:
    return build_styles(theme)
