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
    exp_days = as_int(ce.get("expiring_in_30_days"))
    cert_packs = as_int(ce.get("total_certificate_packs"))

    if cert_packs == 0:
        add_takeaway(ctx, SECT_RISKS, "warning", "cert_presence", state="risk")

    if 0 < exp_days <= CERT_EXPIRY_CRITICAL_DAYS:
        add_takeaway(ctx, SECT_RISKS, "critical", "cert_expire_14", state="risk", days=exp_days)
    elif CERT_EXPIRY_CRITICAL_DAYS < exp_days <= CERT_EXPIRY_WARNING_DAYS:
        add_takeaway(ctx, SECT_RISKS, "warning", "cert_expire_30", state="risk", days=exp_days)

    if ce.get("unavailable") is not True and exp_days > 0:
        add_action(ctx, "info", "cert_expire_30", state="action")
