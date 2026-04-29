"""Security stream rules: threat activity, mitigation rate.

Only evaluated when the ``security`` stream is present in the report.
"""

from __future__ import annotations

from cloudflare_executive_report.common.constants import (
    MITIGATION_RATE_PCT_THRESHOLD,
    THREATS_DELTA_PCT_THRESHOLD,
    TRAFFIC_FLAT_DELTA_PCT,
)
from cloudflare_executive_report.common.safe_types import as_dict, as_float, as_int
from cloudflare_executive_report.executive.rules import (
    SECT_DELTAS,
    SECT_SIGNALS,
)
from cloudflare_executive_report.executive.rules._context import (
    RuleContext,
    add_takeaway,
    percent_delta,
)


def evaluate(ctx: RuleContext) -> None:
    """Evaluate security stream rules. No-op when security stream is absent."""
    if not ctx.available_streams.get("security", False):
        return

    sec = as_dict(ctx.current_zone.get("security"))
    http = as_dict(ctx.current_zone.get("http"))
    mitigation = as_float(sec.get("mitigation_rate_pct"))

    if mitigation > MITIGATION_RATE_PCT_THRESHOLD:
        add_takeaway(
            ctx,
            SECT_SIGNALS,
            "warning",
            "threat_activity",
            state="observation",
            mitigation_pct=round(mitigation, 1),
        )

    # ------------------------------------------------------------------
    # Security / threats deltas
    # Note: this is a cross reference with the http deltas, use both for a full
    # picture of threats vs traffic
    # ------------------------------------------------------------------
    if ctx.previous_zone and ctx.comparison_allowed:
        p_sec = as_dict(ctx.previous_zone.get("security"))
        p_http = as_dict(ctx.previous_zone.get("http"))

        pct_threats = percent_delta(
            as_int(sec.get("mitigated_count")),
            as_int(p_sec.get("mitigated_count")),
        )
        # Threats delta is only meaningful alongside traffic context
        pct_traffic_ref = (
            percent_delta(
                as_int(http.get("total_requests")),
                as_int(p_http.get("total_requests")),
            )
            if ctx.available_streams.get("http", False)
            else 0.0
        )

        if pct_threats > THREATS_DELTA_PCT_THRESHOLD:
            pt = round(pct_threats)
            if abs(pct_traffic_ref) < TRAFFIC_FLAT_DELTA_PCT:
                add_takeaway(
                    ctx,
                    SECT_DELTAS,
                    "critical",
                    "threats_vs_traffic_flat",
                    state="comparison",
                    pct=pt,
                )
            else:
                add_takeaway(
                    ctx,
                    SECT_DELTAS,
                    "warning",
                    "threats_vs_traffic_up",
                    state="comparison",
                    pct=pt,
                )
