"""Per-day security cache via ``httpRequestsAdaptiveGroups`` (eyeball + mitigating filters)."""

from __future__ import annotations

from datetime import date
from typing import Any, ClassVar

from cloudflare_executive_report.cf_client import (
    CloudflareAPIError,
    CloudflareClient,
    CloudflareRateLimitError,
)
from cloudflare_executive_report.common.constants import MITIGATING_SECURITY_ACTIONS
from cloudflare_executive_report.common.dates import (
    day_bounds_utc,
    day_start_iso_z,
    format_ymd,
    utc_now_z,
    utc_today,
)
from cloudflare_executive_report.common.retention import date_outside_security_retention
from cloudflare_executive_report.fetchers.graphql_common import (
    adaptive_groups_rows,
    counts_to_sorted_value_rows,
    group_dimension_table,
    marginal_counts_for_dimension,
    viewer_first_zone,
    zone_alias_groups,
)

# Matrix fold: only these ``securityAction`` values count as mitigated
# (match ``securityAction_in`` below).
EYEBALL_MITIGATING_SECURITY_ACTIONS = MITIGATING_SECURITY_ACTIONS
# Pass traffic: ``cacheStatus`` values treated like Security Analytics "Served by origin"
# (dynamic / cache miss / cache bypass path). All other pass rows count as "Served by Cloudflare"
# (edge-handled: cached, none, redirects-as-edge, etc.). See Cloudflare Traffic analysis docs.
EYEBALL_ORIGIN_FETCH_CACHE_STATUSES = frozenset({"dynamic", "miss", "bypass"})
# GraphQL ``securityAction_in`` for mitigating-only group queries
# (same set as matrix mitigated bucket).
MITIGATING_SECURITY_ACTIONS_GQL = ", ".join(
    f'"{a}"' for a in sorted(EYEBALL_MITIGATING_SECURITY_ACTIONS)
)
# Rollup: omit from ``actions_among_mitigated`` (e.g. AI Labyrinth noise).
ROLLUP_EXCLUDE_ACTION_PREFIXES = ("link_maze_",)
# Rollup: treat action name as challenge if lowercased name contains any of these.
ROLLUP_CHALLENGE_SUBSTRINGS = ("challenge", "captcha")

_LIMIT_TOP_IPS = 10
_LIMIT_TOP_PATHS = 10
_LIMIT_TOP_COUNTRIES = 50
_LIMIT_ACTION_SOURCE = 50


def _gql_mitigating_groups(
    operation_name: str, alias: str, limit: int, dimension_fields: str
) -> str:
    # WARNING: Uses string interpolation for GraphQL.
    # Only use for trusted internal constants (aliases, field names, limits).
    # Do NOT pass unsanitized user input into these fields.
    actions = MITIGATING_SECURITY_ACTIONS_GQL
    return f"""
query {operation_name}($zoneTag: String!, $datetime_geq: Time!, $datetime_lt: Time!) {{
  viewer {{
    zones(filter: {{zoneTag_in: [$zoneTag]}}) {{
      {alias}: httpRequestsAdaptiveGroups(
        limit: {limit}
        filter: {{
          datetime_geq: $datetime_geq
          datetime_lt: $datetime_lt
          requestSource: "eyeball"
          securityAction_in: [{actions}]
        }}
        orderBy: [count_DESC]
      ) {{
        count
        dimensions {{ {dimension_fields} }}
      }}
    }}
  }}
}}
"""


Q_SEC_ACTION_SOURCE = _gql_mitigating_groups(
    "SecHttpActSrc", "asg", _LIMIT_ACTION_SOURCE, "securityAction securitySource"
)
Q_SEC_IPS = _gql_mitigating_groups(
    "SecHttpIps", "ipg", _LIMIT_TOP_IPS, "clientIP clientCountryName"
)
Q_SEC_PATHS = _gql_mitigating_groups("SecHttpPaths", "pth", _LIMIT_TOP_PATHS, "clientRequestPath")
Q_SEC_COUNTRIES = _gql_mitigating_groups(
    "SecHttpCountries", "geo", _LIMIT_TOP_COUNTRIES, "clientCountryName"
)

Q_EYEBALL_MATRIX = """
query SecEyeballMatrix($zoneTag: String!, $datetime_geq: Time!, $datetime_lt: Time!) {
  viewer {
    zones(filter: {zoneTag_in: [$zoneTag]}) {
      mtx: httpRequestsAdaptiveGroups(
        limit: 10000
        filter: {
          datetime_geq: $datetime_geq
          datetime_lt: $datetime_lt
          requestSource: "eyeball"
        }
        orderBy: [count_DESC]
      ) {
        count
        dimensions { securityAction cacheStatus }
      }
    }
  }
}
"""

Q_EYEBALL_METHODS = """
query SecEyeballMethods($zoneTag: String!, $datetime_geq: Time!, $datetime_lt: Time!) {
  viewer {
    zones(filter: {zoneTag_in: [$zoneTag]}) {
      met: httpRequestsAdaptiveGroups(
        limit: 50
        filter: {
          datetime_geq: $datetime_geq
          datetime_lt: $datetime_lt
          requestSource: "eyeball"
        }
        orderBy: [count_DESC]
      ) {
        count
        dimensions { clientRequestHTTPMethodName }
      }
    }
  }
}
"""


def _marginals_from_action_source_rows(
    rows: list[dict[str, Any]],
) -> tuple[dict[str, int], dict[str, int]]:
    by_action: dict[str, int] = {}
    by_source: dict[str, int] = {}
    for row in rows:
        act = str(row.get("securityAction") or "").strip()
        src = str(row.get("securitySource") or "").strip()
        c = int(row.get("count") or 0)
        if act:
            by_action[act] = by_action.get(act, 0) + c
        if src:
            by_source[src] = by_source.get(src, 0) + c
    return by_action, by_source


def _ip_rows_allow_missing_country(zone: dict[str, Any], alias: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in zone_alias_groups(zone, alias):
        dims = row.get("dimensions") or {}
        if not isinstance(dims, dict):
            continue
        ip = dims.get("clientIP")
        if ip is None or not str(ip).strip():
            continue
        co = dims.get("clientCountryName")
        co_s = str(co).strip() if co is not None else ""
        out.append(
            {
                "clientIP": str(ip).strip(),
                "clientCountryName": co_s,
                "count": int(row.get("count") or 0),
            }
        )
    return out


def _fold_eyeball_matrix(rows: list[dict[str, Any]]) -> tuple[int, int, int]:
    """Split eyeball matrix into mitigated vs pass, then pass by origin-fetch vs Cloudflare-served.

    Mitigated uses ``EYEBALL_MITIGATING_SECURITY_ACTIONS`` (same as mitigating GraphQL groups).
    Pass traffic uses ``cacheStatus``: ``EYEBALL_ORIGIN_FETCH_CACHE_STATUSES`` → ``served_origin``;
    all other pass statuses → ``served_cf`` (aligns with Security Analytics Traffic analysis in
    practice: origin bucket ≈ dynamic/miss/bypass marginals). Missing ``securityAction`` is pass.
    """
    mitigated = served_cf = served_origin = 0
    for row in rows:
        c = int(row.get("count") or 0)
        dims = row.get("dimensions") or {}
        if not isinstance(dims, dict):
            continue
        sa = str(dims.get("securityAction") or "").strip().lower()
        cs = str(dims.get("cacheStatus") or "").strip().lower()
        if sa and sa in EYEBALL_MITIGATING_SECURITY_ACTIONS:
            mitigated += c
        elif cs in EYEBALL_ORIGIN_FETCH_CACHE_STATUSES:
            served_origin += c
        else:
            served_cf += c
    return mitigated, served_cf, served_origin


def fetch_security_for_bounds(
    client: CloudflareClient,
    zone_id: str,
    since_iso_z: str,
    until_iso_z: str,
) -> dict[str, Any]:
    """Half-open ``[since_iso_z, until_iso_z)`` as GraphQL ``datetime_geq`` / ``datetime_lt``."""
    vars_gql = {"zoneTag": zone_id, "datetime_geq": since_iso_z, "datetime_lt": until_iso_z}

    matrix_rows = adaptive_groups_rows(client.graphql(Q_EYEBALL_MATRIX, vars_gql), "mtx")
    mitigated, served_cf, served_origin = _fold_eyeball_matrix(matrix_rows)
    sampled_total = mitigated + served_cf + served_origin

    method_rows = adaptive_groups_rows(client.graphql(Q_EYEBALL_METHODS, vars_gql), "met")
    act_src = group_dimension_table(
        viewer_first_zone(client.graphql(Q_SEC_ACTION_SOURCE, vars_gql)),
        "asg",
        ("securityAction", "securitySource"),
    )
    ba, bs = _marginals_from_action_source_rows(act_src)

    ip_rows = _ip_rows_allow_missing_country(
        viewer_first_zone(client.graphql(Q_SEC_IPS, vars_gql)),
        "ipg",
    )
    path_rows = adaptive_groups_rows(client.graphql(Q_SEC_PATHS, vars_gql), "pth")
    geo_rows = adaptive_groups_rows(client.graphql(Q_SEC_COUNTRIES, vars_gql), "geo")

    return {
        "http_requests_sampled": sampled_total,
        "mitigated_count": mitigated,
        "served_cf_count": served_cf,
        "served_origin_count": served_origin,
        "http_by_cache_status": marginal_counts_for_dimension(matrix_rows, "cacheStatus"),
        "by_http_method": marginal_counts_for_dimension(method_rows, "clientRequestHTTPMethodName")
        if method_rows
        else [],
        "by_action": counts_to_sorted_value_rows(ba),
        "by_source": counts_to_sorted_value_rows(bs),
        "attack_source_buckets": [
            {
                "ip": r["clientIP"],
                "country": r["clientCountryName"],
                "count": int(r["count"] or 0),
            }
            for r in ip_rows
        ],
        "by_attack_path": marginal_counts_for_dimension(path_rows, "clientRequestPath"),
        "by_attack_country": marginal_counts_for_dimension(geo_rows, "clientCountryName"),
        "payload_kind": "http_security_groups",
    }


def fetch_security_for_date(
    client: CloudflareClient,
    zone_id: str,
    day: date,
) -> dict[str, Any]:
    geq, lt = day_bounds_utc(day)
    payload = fetch_security_for_bounds(client, zone_id, geq, lt)
    payload["date"] = format_ymd(day)
    return payload


class SecurityFetcher:
    stream_id: ClassVar[str] = "security"
    cache_filename: ClassVar[str] = "security.json"
    collect_label: ClassVar[str] = "Security"
    required_permissions: ClassVar[tuple[str, ...]] = (
        "Zone > Zone Read",
        "Zone > Analytics Read",
    )

    def outside_retention(self, day: date, *, plan_legacy_id: str | None) -> bool:
        return date_outside_security_retention(day, plan_legacy_id=plan_legacy_id)

    def fetch(
        self,
        client: CloudflareClient,
        zone_id: str,
        day: date,
        *,
        zone_meta: dict[str, Any] | None,
    ) -> dict[str, Any]:
        _ = zone_meta
        return fetch_security_for_date(client, zone_id, day)

    def append_live_today(
        self,
        client: CloudflareClient,
        zone_id: str,
        zone_name: str,
        *,
        plan_legacy_id: str | None,
        zone_meta: dict[str, Any] | None,
    ) -> tuple[list[dict[str, Any]], list[str], bool]:
        _ = zone_meta
        t = utc_today()
        if date_outside_security_retention(t, plan_legacy_id=plan_legacy_id):
            return [], [], False
        try:
            payload = fetch_security_for_bounds(
                client,
                zone_id,
                day_start_iso_z(t),
                utc_now_z(),
            )
            payload["date"] = format_ymd(t)
            return (
                [payload],
                [
                    "Report includes today's UTC date; "
                    "security analytics may be incomplete until the day finishes."
                ],
                False,
            )
        except CloudflareRateLimitError:
            return (
                [],
                [f"Could not fetch today's security data for zone {zone_name} (rate limited)."],
                True,
            )
        except CloudflareAPIError as e:
            return ([], [f"Could not fetch today's security data for zone {zone_name}: {e}"], False)
