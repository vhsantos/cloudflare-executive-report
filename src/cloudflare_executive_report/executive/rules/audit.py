"""Audit stream rules: audit event volume.

Only evaluated when the ``audit`` stream is present in the report.
"""

from __future__ import annotations

from cloudflare_executive_report.common.constants import AUDIT_EVENTS_THRESHOLD
from cloudflare_executive_report.common.safe_types import as_dict, as_int
from cloudflare_executive_report.executive.rules import SECT_SIGNALS
from cloudflare_executive_report.executive.rules._context import (
    RuleContext,
    add_action,
    add_takeaway,
)


def evaluate(ctx: RuleContext) -> None:
    """Evaluate audit stream rules. No-op when audit stream is absent."""
    if not ctx.available_streams.get("audit", False):
        return

    au = as_dict(ctx.current_zone.get("audit"))
    audits = as_int(au.get("total_events"))

    if audits > AUDIT_EVENTS_THRESHOLD:
        add_takeaway(
            ctx, SECT_SIGNALS, "warning", "audit_activity", state="observation", events=audits
        )
        if au.get("unavailable") is not True:
            add_action(ctx, "info", "audit_activity", state="action")
