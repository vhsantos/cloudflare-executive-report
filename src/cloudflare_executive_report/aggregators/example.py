"""Skeleton aggregator - copy this when adding a new stream.

Replace ``example`` / ``Example`` with your stream name and fill in the
real field mappings from your fetcher payload.
"""

from __future__ import annotations

from typing import Any

from cloudflare_executive_report.common.formatting import format_count_human


def build_example_section(
    daily_api_data: list[dict[str, Any]],
    *,
    top: int = 10,
) -> dict[str, Any]:
    """Aggregate example daily payloads into one report section.

    ``daily_api_data`` is a list of ``data`` blobs exactly as stored by
    ``ExampleFetcher.fetch``.  Never call the Cloudflare API here.
    """
    total_count = 0
    dimension_counts: dict[str, int] = {}

    for day in daily_api_data:
        total_count += int(day.get("total_count") or 0)

        for row in day.get("by_example_dimension") or []:
            if not isinstance(row, dict):
                continue
            key = str(row.get("value") or "").strip()
            if not key:
                continue
            dimension_counts[key] = dimension_counts.get(key, 0) + int(row.get("count") or 0)

    top_dimensions: list[dict[str, Any]] = [
        {
            "value": k,
            "count": v,
            "percentage": round(100.0 * v / total_count, 1) if total_count > 0 else 0.0,
        }
        for k, v in sorted(dimension_counts.items(), key=lambda x: -x[1])[:top]
    ]

    return {
        "total_count": total_count,
        "total_count_human": format_count_human(total_count),
        "top_dimensions": top_dimensions,
    }
