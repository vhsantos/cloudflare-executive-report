"""Cloudflare Analytics GraphQL helpers: first zone and adaptive *Groups row parsing."""

from __future__ import annotations

from typing import Any


def viewer_first_zone(data: dict[str, Any] | None) -> dict[str, Any]:
    """First zone object under ``data.viewer.zones``, or empty dict."""
    if not data:
        return {}
    zones = ((data.get("viewer") or {}).get("zones")) or []
    if not zones:
        return {}
    z = zones[0]
    return z if isinstance(z, dict) else {}


def zone_alias_groups(zone: dict[str, Any], alias: str) -> list[dict[str, Any]]:
    """List of group row dicts under ``zone[alias]`` (GraphQL query alias)."""
    rows = zone.get(alias)
    if not isinstance(rows, list):
        return []
    return [r for r in rows if isinstance(r, dict)]


def adaptive_groups_rows(data: dict[str, Any] | None, alias: str) -> list[dict[str, Any]]:
    """``httpRequestsAdaptiveGroups`` (or similar) rows from a full GraphQL ``data`` payload."""
    return zone_alias_groups(viewer_first_zone(data), alias)


def marginal_counts_for_dimension(
    rows: list[dict[str, Any]], dimension_field: str
) -> list[dict[str, Any]]:
    """
    Roll up raw adaptive group rows to sorted ``[{"value", "count"}, ...]`` for one dimension.
    Skips empty dimension values.
    """
    counts: dict[str, int] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        dims = row.get("dimensions") or {}
        if not isinstance(dims, dict):
            continue
        key = str(dims.get(dimension_field) or "").strip()
        if not key:
            continue
        c = int(row.get("count") or 0)
        counts[key] = counts.get(key, 0) + c
    ordered = sorted(counts.items(), key=lambda x: -x[1])
    return [{"value": k, "count": v} for k, v in ordered]


def counts_to_sorted_value_rows(counts: dict[str, int]) -> list[dict[str, Any]]:
    """``[{"value", "count"}, ...]`` descending by count (cache / aggregate table shape)."""
    items = sorted(counts.items(), key=lambda x: -x[1])
    return [{"value": k, "count": c} for k, c in items]


def group_dimension_table(
    zone: dict[str, Any],
    alias: str,
    dim_keys: tuple[str, ...],
) -> list[dict[str, Any]]:
    """
    Flatten adaptive group rows to dicts with dimension fields plus ``count``.

    Rows missing ANY requested dimension are silently skipped. This matches
    Cloudflare's behavior where dimensions may be null for certain groupings
    (e.g., clientCountryName null for non-geo traffic).

    Example input row:
        {"dimensions": {"clientIP": "1.2.3.4", "clientCountryName": "US"}, "count": 100}

    Example output:
        {"clientIP": "1.2.3.4", "clientCountryName": "US", "count": 100}

    Args:
        zone: The zone object from GraphQL response (viewer.zones[0])
        alias: The query alias used for this group
        dim_keys: Tuple of dimension field names to extract
            (e.g. ``("clientIP", "clientCountryName")``)

    Returns:
        List of dicts, each containing the requested dimension keys plus a "count" field.
        Empty list if zone, alias, or dimensions are missing/invalid.
    """
    out: list[dict[str, Any]] = []
    for row in zone_alias_groups(zone, alias):
        dims = row.get("dimensions") or {}
        if not isinstance(dims, dict):
            continue
        keys: dict[str, str] = {}
        ok = True
        for k in dim_keys:
            v = dims.get(k)
            if v is None:
                ok = False
                break
            keys[k] = str(v)
        if not ok:
            continue
        c = int(row.get("count") or 0)
        out.append({**keys, "count": c})
    return out


def table_rows_to_value_counts(rows: list[dict[str, Any]], value_key: str) -> list[dict[str, Any]]:
    """``[{value_key, count}, ...]`` for value/count tables in cached JSON."""
    return [{"value": r[value_key], "count": r["count"]} for r in rows if value_key in r]


def row_sum_int(row: dict[str, Any], sum_field: str) -> int:
    """Safe int extractor for ``row["sum"][sum_field]`` in GraphQL group rows."""
    sums = row.get("sum") or {}
    if not isinstance(sums, dict):
        return 0
    return int(sums.get(sum_field) or 0)


def marginal_counts_and_sums_for_dimension(
    rows: list[dict[str, Any]],
    dimension_field: str,
    *,
    sum_field: str,
    out_sum_key: str,
) -> list[dict[str, Any]]:
    """
    Roll up rows to ``[{"value", "count", out_sum_key}, ...]`` for one dimension.
    Skips empty dimension values.
    """
    counts: dict[str, int] = {}
    sums: dict[str, int] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        dims = row.get("dimensions") or {}
        if not isinstance(dims, dict):
            continue
        key = str(dims.get(dimension_field) or "").strip()
        if not key:
            continue
        counts[key] = counts.get(key, 0) + int(row.get("count") or 0)
        sums[key] = sums.get(key, 0) + row_sum_int(row, sum_field)
    ordered = sorted(counts.items(), key=lambda x: -x[1])
    return [{"value": k, "count": c, out_sum_key: int(sums.get(k) or 0)} for k, c in ordered]
