"""Shared appendix page for executive PDF reports."""

from __future__ import annotations

from typing import Any

from reportlab.platypus import Paragraph, Spacer

from cloudflare_executive_report.common.constants import PDF_SPACE_MEDIUM_PT
from cloudflare_executive_report.pdf.primitives import get_render_context
from cloudflare_executive_report.pdf.theme import Theme


def aggregate_nist_reference_rows(zone_summaries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return unique NIST reference rows across zones, sorted by NIST id."""
    merged_rows: dict[str, dict[str, Any]] = {}
    for zone_summary in zone_summaries:
        raw_rows = zone_summary.get("nist_reference")
        if not isinstance(raw_rows, list):
            continue
        for raw_row in raw_rows:
            if not isinstance(raw_row, dict):
                continue
            nist_id = str(raw_row.get("nist_id") or "").strip()
            if not nist_id:
                continue
            raw_check_ids = raw_row.get("check_ids")
            check_ids = (
                sorted({str(value).strip() for value in raw_check_ids if str(value).strip()})
                if isinstance(raw_check_ids, list)
                else []
            )
            existing_row = merged_rows.get(nist_id)
            if existing_row is None:
                merged_rows[nist_id] = {
                    "nist_id": nist_id,
                    "title": str(raw_row.get("title") or "").strip(),
                    "url": str(raw_row.get("url") or "").strip(),
                    "check_ids": check_ids,
                }
                continue
            existing_check_ids = {
                str(value).strip()
                for value in (existing_row.get("check_ids") or [])
                if str(value).strip()
            }
            existing_row["check_ids"] = sorted(existing_check_ids.union(check_ids))
            if not str(existing_row.get("title") or "").strip():
                existing_row["title"] = str(raw_row.get("title") or "").strip()
            if not str(existing_row.get("url") or "").strip():
                existing_row["url"] = str(raw_row.get("url") or "").strip()
    return [merged_rows[nist_id] for nist_id in sorted(merged_rows.keys())]


def include_report_appendix(
    story: list[Any],
    *,
    theme: Theme,
    metric_notes: list[str],
    nist_reference_rows: list[dict[str, Any]],
) -> None:
    """Append one shared appendix page with metric notes and NIST references."""
    styles = get_render_context().styles
    story.append(Paragraph("Appendix", styles["RepStreamHeadLeft"]))
    story.append(Spacer(1, PDF_SPACE_MEDIUM_PT))
    if metric_notes:
        story.append(Paragraph("Metric notes", styles["RepSection"]))
        for note in metric_notes:
            story.append(Paragraph(f"- {note}", styles["RepTableCell"]))
        story.append(Spacer(1, PDF_SPACE_MEDIUM_PT))
    if nist_reference_rows:
        story.append(Paragraph("Security Controls Reference (NIST 800-53)", styles["RepSection"]))
        for row in nist_reference_rows:
            nist_id = str(row.get("nist_id") or "")
            title = str(row.get("title") or "")
            url = str(row.get("url") or "").strip()
            raw_ids = row.get("check_ids") or []
            checks = ", ".join(str(value) for value in raw_ids) if isinstance(raw_ids, list) else ""
            label = f"[{nist_id}]"
            if url:
                text = f'<a href="{url}" color="{theme.primary}">{label}</a>'
            else:
                text = label
            if title:
                text += f" {title}"
            if checks:
                text += f" ({checks})"
            story.append(Paragraph(text, styles["RepTableCell"]))
