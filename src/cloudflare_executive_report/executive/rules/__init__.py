"""Comparison and posture rules for the executive summary (takeaways + actions).

This is the public interface for the rules engine. All types and helpers
used by callers (tests, summary.py) are defined here and importable from
``cloudflare_executive_report.executive.rules``.

Stream-specific logic lives in per-stream sub-modules; this orchestrator
builds a ``RuleContext``, calls each module, then assembles the final output.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

from cloudflare_executive_report.common.safe_types import as_dict
from cloudflare_executive_report.executive.phrase_catalog import get_phrase

_VALID_SEVERITIES = frozenset({"positive", "warning", "critical", "info"})
_TOKEN_KEY = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")

# ---------------------------------------------------------------------------
# Section identifiers
# ---------------------------------------------------------------------------
# Report section IDs: string keys in takeaways_categorized JSON and ExecutiveLine.section.
# These are NOT severities. Severity (positive, warning, critical, info) is separate; it drives
# the [OK]/[!] prefix and tone. Section only decides which bucket a line appears in and merge
# order in the flat takeaways list (see TX_ORDER).
#
# SECT_WINS ("wins"): Improvements versus the previous report period (traffic up, latency down,
# apex proxied, SSL upgraded, DNSSEC enabled). Only emitted when comparison is allowed.
#
# SECT_RISKS ("risks"): Current-zone configuration and exposure issues (SSL mode, WAF off, apex
# unproxied, cert expiry). Comparison gate messages live in SECT_DELTAS so they do not affect
# security posture score (risks-only).
#
# SECT_SIGNALS ("signals"): Multiple observations combined in one narrative (origin errors+latency,
# cache + bandwidth, security level notes, threat rate spikes). Not the same as period deltas.
#
# SECT_DELTAS ("deltas"): Period-over-period metric deltas (traffic/threats/latency/cache vs last
# window). Includes the optional baseline line ("Comparing to: ...") when comparison is allowed.
#
# SECT_ACTIONS ("actions"): Recommended next steps only. Shown under "actions" in JSON, not mixed
# into the numbered takeaway paragraphs for PDF (flat takeaways list excludes this section).
SECT_WINS: TakeawaySection = "wins"
SECT_RISKS: TakeawaySection = "risks"
SECT_SIGNALS: TakeawaySection = "signals"
SECT_DELTAS: TakeawaySection = "deltas"
SECT_ACTIONS = "actions"


# Flatten order for PDF and the flat takeaways list.
TX_ORDER: tuple[str, ...] = (SECT_WINS, SECT_RISKS, SECT_SIGNALS, SECT_DELTAS)

TakeawaySection = Literal["wins", "risks", "signals", "deltas"]


def _period_days(period: dict[str, Any]) -> int:
    start = str(period.get("start") or "")
    end = str(period.get("end") or "")
    if not start or not end:
        return 0
    from cloudflare_executive_report.common.dates import parse_ymd

    try:
        return (parse_ymd(end) - parse_ymd(start)).days + 1
    except Exception:
        return 0


def _period_bounds(period: dict[str, Any]) -> tuple[date, date] | None:
    start = str(period.get("start") or "")
    end = str(period.get("end") or "")
    if not start or not end:
        return None
    from cloudflare_executive_report.common.dates import parse_ymd

    try:
        return parse_ymd(start), parse_ymd(end)
    except Exception:
        return None


@dataclass(frozen=True)
class ExecutiveMessageFilter:
    """Exact keys and regex patterns that suppress executive lines."""

    exact_keys: frozenset[str]
    patterns: tuple[re.Pattern[str], ...]

    @classmethod
    def empty(cls) -> ExecutiveMessageFilter:
        return cls(frozenset(), ())

    @classmethod
    def from_entries(cls, entries: Sequence[str] | None) -> ExecutiveMessageFilter:
        """Token-shaped entries match the key exactly; anything else is a regex (re.search)."""
        if not entries:
            return cls.empty()
        exact: set[str] = set()
        patterns: list[re.Pattern[str]] = []
        for raw in entries:
            s = str(raw).strip()
            if not s:
                continue
            if _TOKEN_KEY.fullmatch(s):
                exact.add(s)
            else:
                patterns.append(re.compile(s))
        return cls(frozenset(exact), tuple(patterns))

    def is_ignored(self, phrase_key: str) -> bool:
        if phrase_key in self.exact_keys:
            return True
        return any(p.search(phrase_key) for p in self.patterns)


@dataclass(frozen=True, slots=True)
class ExecutiveLine:
    """One executive line: ids, NIST tags, severity, rendered body, and report section."""

    phrase_key: str
    state: str
    check_id: str
    service: str
    nist: tuple[str, ...]
    severity: str
    body: str
    section: str


@dataclass(frozen=True, slots=True)
class ExecutiveRuleOutput:
    """Rule output: ordered takeaway lines, then actions (JSON uses action bodies only)."""

    takeaways: tuple[ExecutiveLine, ...]
    actions: tuple[ExecutiveLine, ...]

    def lines_for_section(self, section: str) -> list[ExecutiveLine]:
        """Lines in one takeaway section (for tests and JSON grouping)."""
        return [ln for ln in self.takeaways if ln.section == section]


@dataclass
class ComparisonGate:
    allowed: bool
    blocked_takeaway: ExecutiveLine | None


def exec_msg(
    severity: str,
    phrase_key: str,
    *,
    state: str,
    section: str,
    filt: ExecutiveMessageFilter | None = None,
    **kwargs: object,
) -> ExecutiveLine | None:
    """Render a phrase if not ignored. Severity sets the [OK]/[!] prefix; section is the group."""
    if severity not in _VALID_SEVERITIES:
        allowed = ", ".join(sorted(_VALID_SEVERITIES))
        raise ValueError(f"Invalid severity {severity!r}; expected one of: {allowed}")
    if filt is not None and filt.is_ignored(phrase_key):
        return None
    phrase_data = get_phrase(phrase_key, state)
    text = phrase_data["text"]
    if not isinstance(text, str):
        raise ValueError(f"Phrase text for {phrase_key!r} state {state!r} must be a string")
    nist_raw = phrase_data["nist"]
    if not isinstance(nist_raw, list):
        raise TypeError(f"Phrase nist for {phrase_key!r} state {state!r} must be a list")
    return ExecutiveLine(
        phrase_key=phrase_key,
        state=state,
        check_id=str(phrase_data["id"]),
        service=str(phrase_data["service"]),
        nist=tuple(str(x) for x in nist_raw),
        severity=severity,
        body=text.format(**kwargs),
        section=section,
    )


def _comparison_gate_blocked(
    phrase_key: str,
    filt: ExecutiveMessageFilter | None,
    **phrase_kwargs: object,
) -> ComparisonGate:
    """Return disallowed comparison with one deltas-section takeaway (warning)."""
    line = exec_msg(
        "warning", phrase_key, state="comparison", section=SECT_DELTAS, filt=filt, **phrase_kwargs
    )
    return ComparisonGate(allowed=False, blocked_takeaway=line)


def evaluate_comparison_gate(
    *,
    current_zone_id: str,
    previous_report: dict[str, Any] | None,
    current_period: dict[str, Any],
    message_filter: ExecutiveMessageFilter | None = None,
) -> ComparisonGate:
    """Whether prior-period comparison is allowed; otherwise one posture takeaway explaining why."""
    filt = message_filter
    if not previous_report:
        return _comparison_gate_blocked("comparison_first_report", filt)

    previous_period = as_dict(previous_report.get("report_period"))
    current_days = _period_days(current_period)
    previous_days = _period_days(previous_period)
    previous_bounds = _period_bounds(previous_period)
    current_bounds = _period_bounds(current_period)
    bounds_bad = (
        previous_bounds is None or current_bounds is None or previous_bounds[1] >= current_bounds[0]
    )

    days_bad = current_days <= 0 or previous_days <= 0 or current_days != previous_days
    if bounds_bad or days_bad:
        return _comparison_gate_blocked(
            "comparison_period_mismatch",
            filt,
            previous_days=previous_days,
            current_days=current_days,
        )

    prev_zone = _find_zone(previous_report, current_zone_id)
    if not prev_zone:
        return _comparison_gate_blocked("comparison_first_report", filt)

    return ComparisonGate(allowed=True, blocked_takeaway=None)


def _find_zone(report: dict[str, Any], zone_id: str) -> dict[str, Any] | None:
    for zone in report.get("zones") or []:
        if isinstance(zone, dict) and str(zone.get("zone_id") or "") == zone_id:
            return zone
    return None


def build_executive_rule_output(
    *,
    current_zone: dict[str, Any],
    previous_zone: dict[str, Any] | None,
    comparison_allowed: bool,
    message_filter: ExecutiveMessageFilter | None = None,
    gate_warning: ExecutiveLine | None = None,
    comparison_baseline: ExecutiveLine | None = None,
    available_streams: dict[str, bool] | None = None,
) -> ExecutiveRuleOutput:
    """Run posture and comparison rules; return ordered takeaways and actions.

    When ``available_streams`` is provided, stream-specific rules are skipped for
    absent streams. Zone-health rules always run. When ``available_streams`` is
    None (legacy call sites / tests without stream filtering), all rules run.
    """
    # Sub-module imports are deferred to avoid circular import at package load time.
    from cloudflare_executive_report.executive.rules import audit as _audit
    from cloudflare_executive_report.executive.rules import certificates as _certificates
    from cloudflare_executive_report.executive.rules import dns as _dns
    from cloudflare_executive_report.executive.rules import email as _email
    from cloudflare_executive_report.executive.rules import http as _http
    from cloudflare_executive_report.executive.rules import security as _security
    from cloudflare_executive_report.executive.rules import zone_health as _zone_health
    from cloudflare_executive_report.executive.rules._context import RuleContext

    filt = message_filter or ExecutiveMessageFilter.empty()
    sections: dict[str, list[ExecutiveLine]] = {k: [] for k in TX_ORDER}
    actions: list[ExecutiveLine] = []

    # When called without available_streams (e.g. tests that pre-date this argument),
    # treat all streams as available so no rules are skipped.
    streams: dict[str, bool] = (
        available_streams
        if available_streams is not None
        else {
            "http": True,
            "http_adaptive": True,
            "security": True,
            "dns": True,
            "dns_records": True,
            "cache": True,
            "email": True,
            "audit": True,
            "certificates": True,
        }
    )

    ctx = RuleContext(
        current_zone=current_zone,
        previous_zone=previous_zone,
        available_streams=streams,
        comparison_allowed=comparison_allowed,
        filt=filt,
        sections=sections,
        actions=actions,
    )

    # Zone-health rules always run (fetched for every report regardless of --types).
    _zone_health.evaluate(ctx)

    # Stream-specific rules: only when the stream was requested/synced.
    _http.evaluate(ctx)
    _security.evaluate(ctx)
    _email.evaluate(ctx)
    _certificates.evaluate(ctx)
    _audit.evaluate(ctx)
    _dns.evaluate(ctx)

    # Insert comparison gate messages at the top of the deltas section.
    if gate_warning is not None:
        sections[SECT_DELTAS].insert(0, gate_warning)
    if comparison_baseline is not None:
        sections[SECT_DELTAS].insert(0, comparison_baseline)

    merged_takeaways = [ln for key in TX_ORDER for ln in sections[key]]
    return ExecutiveRuleOutput(
        takeaways=tuple(merged_takeaways),
        actions=tuple(actions),
    )
