"""Email stream rules: DMARC, SPF, DKIM, fail rate, drops.

Only evaluated when the ``email`` stream is present in the report.
"""

from __future__ import annotations

from cloudflare_executive_report.common.safe_types import as_dict
from cloudflare_executive_report.executive.rules import (
    SECT_RISKS,
    SECT_SIGNALS,
    SECT_WINS,
)
from cloudflare_executive_report.executive.rules._context import (
    RuleContext,
    add_action,
    add_takeaway,
)

_EMAIL_FAIL_RATE_THRESHOLD = 10.0


def evaluate(ctx: RuleContext) -> None:
    """Evaluate email stream rules. No-op when email stream is absent."""
    if not ctx.available_streams.get("email", False):
        return

    email = as_dict(ctx.current_zone.get("email"))

    dmarc = str(email.get("dns_dmarc_policy") or "").lower()
    spf = str(email.get("dns_spf_policy") or "").lower()
    dkim = bool(email.get("dns_dkim_configured"))

    if dmarc == "none":
        add_takeaway(ctx, SECT_RISKS, "critical", "email_dmarc_none", state="risk")
        add_action(ctx, "info", "email_dmarc_none", state="action")
    elif dmarc == "quarantine":
        add_takeaway(ctx, SECT_RISKS, "warning", "email_dmarc_quarantine", state="risk")
        add_action(ctx, "info", "email_dmarc_quarantine", state="action")

    if spf == "none":
        add_takeaway(ctx, SECT_RISKS, "warning", "email_spf_missing", state="risk")
        add_action(ctx, "info", "email_spf_missing", state="action")
    elif spf == "softfail":
        add_takeaway(ctx, SECT_SIGNALS, "info", "email_spf_softfail", state="observation")
        add_action(ctx, "info", "email_spf_softfail", state="action")

    if not dkim:
        add_takeaway(ctx, SECT_RISKS, "warning", "email_dkim_missing", state="risk")
        add_action(ctx, "info", "email_dkim_missing", state="action")

    fail_pct = 100.0 - float(email.get("dmarc_pass_rate_pct") or 100.0)
    if fail_pct > _EMAIL_FAIL_RATE_THRESHOLD:
        add_takeaway(
            ctx,
            SECT_SIGNALS,
            "warning",
            "email_high_fail_rate",
            state="observation",
            fail_pct=round(fail_pct, 1),
        )

    dropped = int(email.get("dropped") or 0)
    if dropped > 0:
        add_takeaway(
            ctx, SECT_SIGNALS, "info", "email_routing_drops", state="observation", dropped=dropped
        )

    # ------------------------------------------------------------------
    # Email deltas
    # ------------------------------------------------------------------
    if ctx.previous_zone and ctx.comparison_allowed:
        p_email = as_dict(ctx.previous_zone.get("email"))

        p_dmarc = str(p_email.get("dns_dmarc_policy") or "").lower()
        if p_dmarc in ("none", "quarantine") and dmarc == "reject":
            add_takeaway(
                ctx, SECT_WINS, "positive", "email_dmarc_reject", state="win", previous=p_dmarc
            )

        p_spf = str(p_email.get("dns_spf_policy") or "").lower()
        if p_spf in ("none", "softfail") and spf == "hardfail":
            add_takeaway(
                ctx, SECT_WINS, "positive", "email_spf_hardfail", state="win", previous=p_spf
            )

        p_dkim = bool(p_email.get("dns_dkim_configured"))
        if not p_dkim and dkim:
            add_takeaway(ctx, SECT_WINS, "positive", "email_dkim_configured", state="win")
