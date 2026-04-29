"""Shared rule-evaluation context passed to every stream rule module."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from cloudflare_executive_report.executive.rules import (
        ExecutiveLine,
        ExecutiveMessageFilter,
        TakeawaySection,
    )

from cloudflare_executive_report.executive.rules import (
    SECT_ACTIONS,
    exec_msg,
)


@dataclass
class RuleContext:
    """Mutable accumulator threaded through every stream rule module.

    ``sections`` and ``actions`` are mutated in-place by ``add_takeaway``
    and ``add_action``. All other fields are read-only inputs.
    """

    current_zone: dict[str, Any]
    previous_zone: dict[str, Any] | None
    available_streams: dict[str, bool]
    comparison_allowed: bool
    filt: ExecutiveMessageFilter
    sections: dict[str, list[ExecutiveLine]] = field(default_factory=dict)
    actions: list[ExecutiveLine] = field(default_factory=list)


def add_takeaway(
    ctx: RuleContext,
    section: TakeawaySection,
    severity: str,
    phrase_key: str,
    *,
    state: str,
    **kwargs: object,
) -> None:
    """Render a phrase and append it to the correct section bucket."""
    line = exec_msg(severity, phrase_key, state=state, section=section, filt=ctx.filt, **kwargs)
    if line:
        ctx.sections[section].append(line)


def add_action(
    ctx: RuleContext,
    severity: str,
    phrase_key: str,
    *,
    state: str,
    **kwargs: object,
) -> None:
    """Render a phrase and append it to the actions list."""
    line = exec_msg(
        severity, phrase_key, state=state, section=SECT_ACTIONS, filt=ctx.filt, **kwargs
    )
    if line:
        ctx.actions.append(line)


def percent_delta(current: float, previous: float) -> float:
    """Percentage change from previous to current."""
    if previous == 0:
        return 0.0
    return ((current - previous) / previous) * 100.0


def pp_delta(current: float, previous: float) -> float:
    """Absolute percentage-point delta."""
    return current - previous
