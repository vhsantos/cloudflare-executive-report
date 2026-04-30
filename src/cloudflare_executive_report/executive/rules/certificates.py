"""Certificate stream rules: cert presence and expiry.

Only evaluated when the ``certificates`` stream is present in the report.
"""

from __future__ import annotations

from cloudflare_executive_report.common.constants import (
    CERT_EXPIRY_CRITICAL_DAYS,
    CERT_EXPIRY_WARNING_DAYS,
)
from cloudflare_executive_report.common.safe_types import as_dict, as_int
from cloudflare_executive_report.executive.rules import SECT_RISKS
from cloudflare_executive_report.executive.rules._context import (
    RuleContext,
    add_action,
    add_takeaway,
)


def evaluate(ctx: RuleContext) -> None:
    """Evaluate certificate stream rules. No-op when certificates stream is absent."""
    if not ctx.available_streams.get("certificates", False):
        return

    ce = as_dict(ctx.current_zone.get("certificates"))
    cert_packs = as_int(ce.get("total_certificate_packs"))

    if cert_packs == 0:
        add_takeaway(ctx, SECT_RISKS, "warning", "cert_presence", state="risk")

    soonest = ce.get("soonest_expiry")
    if not soonest:
        return

    from cloudflare_executive_report.common.dates import parse_ymd, utc_today

    # soonest_expiry is ISO 8601 (YYYY-MM-DDTHH:MM:SSZ)
    try:
        expiry_date = parse_ymd(soonest[:10])
        days_left = (expiry_date - utc_today()).days
    except (ValueError, TypeError):
        return

    if days_left <= 0:
        add_takeaway(ctx, SECT_RISKS, "critical", "cert_expired", state="risk")
    elif days_left <= CERT_EXPIRY_CRITICAL_DAYS:
        add_takeaway(ctx, SECT_RISKS, "critical", "cert_expire_14", state="risk", days=days_left)
    elif days_left <= CERT_EXPIRY_WARNING_DAYS:
        add_takeaway(ctx, SECT_RISKS, "warning", "cert_expire_30", state="risk", days=days_left)

    if ce.get("unavailable") is not True and days_left <= CERT_EXPIRY_WARNING_DAYS:
        add_action(ctx, "info", "cert_expire_30", state="action")
