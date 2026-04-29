"""DNS rules/delta and comparisons.

Only active when the dns_records stream is present in the report.
"""

from __future__ import annotations

from cloudflare_executive_report.common.safe_types import as_dict, as_int
from cloudflare_executive_report.executive.rules import (
    SECT_DELTAS,
    SECT_WINS,
)
from cloudflare_executive_report.executive.rules._context import (
    RuleContext,
    add_takeaway,
)


def evaluate(ctx: RuleContext) -> None:
    """Evaluate all comparison delta rules. No-op when comparison is not allowed."""
    if not (ctx.previous_zone and ctx.comparison_allowed):
        return

    dr = as_dict(ctx.current_zone.get("dns_records"))
    p_dr = as_dict(ctx.previous_zone.get("dns_records"))

    # ------------------------------------------------------------------
    # DNS records deltas (apex proxy change)
    # ------------------------------------------------------------------
    if ctx.available_streams.get("dns_records", False):
        p_apex = as_int(p_dr.get("apex_unproxied_a_aaaa"))
        c_apex = as_int(dr.get("apex_unproxied_a_aaaa"))
        if p_apex == 0 and c_apex > 0:
            add_takeaway(
                ctx,
                SECT_DELTAS,
                "critical",
                "apex_proxy",
                state="comparison",
                previous="proxied",
                current="dns-only",
            )
        if p_apex > 0 and c_apex == 0:
            add_takeaway(ctx, SECT_WINS, "positive", "apex_proxy", state="win")
