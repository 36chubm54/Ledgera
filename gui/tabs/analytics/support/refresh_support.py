from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass, field

from ..core.breakdown_section import AnalyticsBreakdownSection
from ..core.contracts import AnalyticsTabContext
from ..core.monthly_section import AnalyticsTimelineSection
from ..core.render import _draw_breakdown_pie, _draw_net_worth_line


@dataclass(slots=True)
class AnalyticsDisplayFormatters:
    display_code: Callable[[], str]
    format_display_amount: Callable[[float, int], str]
    format_display_money: Callable[[float, int], str]


@dataclass(slots=True)
class AnalyticsRefreshState:
    last_timeline_data: list = field(default_factory=list)
    last_breakdown_data: list = field(default_factory=list)
    redraw_job: str | None = None


def build_display_formatters(context: AnalyticsTabContext) -> AnalyticsDisplayFormatters:
    def display_code() -> str:
        getter = getattr(context.controller, "get_display_currency_code", None)
        if callable(getter):
            return str(getter())
        getter = getattr(context.controller, "get_display_currency", None)
        if callable(getter):
            return str(getter())
        return "KZT"

    def format_display_amount(amount: float, precision: int = 0) -> str:
        formatter = getattr(context.controller, "format_display_amount", None)
        if callable(formatter):
            return str(formatter(amount, precision=precision))
        return f"{float(amount):,.{precision}f}"

    def format_display_money(amount: float, precision: int = 0) -> str:
        formatter = getattr(context.controller, "format_display_money", None)
        if callable(formatter):
            try:
                return str(formatter(amount, precision=precision))
            except TypeError:
                return str(formatter(amount, precision))
        return f"{format_display_amount(amount, precision=precision)} {display_code()}"

    return AnalyticsDisplayFormatters(
        display_code=display_code,
        format_display_amount=format_display_amount,
        format_display_money=format_display_money,
    )


def redraw_analytics_canvases(
    *,
    state: AnalyticsRefreshState,
    timeline: AnalyticsTimelineSection,
    breakdown: AnalyticsBreakdownSection,
    formatters: AnalyticsDisplayFormatters,
) -> None:
    state.redraw_job = None
    _draw_net_worth_line(
        timeline.timeline_canvas,
        state.last_timeline_data,
        format_amount=lambda value: formatters.format_display_amount(value, 0),
    )
    _draw_breakdown_pie(
        breakdown.category_canvas,
        state.last_breakdown_data,
        format_amount=lambda value: formatters.format_display_amount(value, 0),
    )


def schedule_analytics_redraw(
    *,
    context: AnalyticsTabContext,
    state: AnalyticsRefreshState,
    timeline: AnalyticsTimelineSection,
    breakdown: AnalyticsBreakdownSection,
    formatters: AnalyticsDisplayFormatters,
) -> None:
    if state.redraw_job is not None:
        try:
            context.after_cancel(state.redraw_job)
        except (tk.TclError, RuntimeError):
            pass
    state.redraw_job = context.after(
        120,
        lambda: redraw_analytics_canvases(
            state=state,
            timeline=timeline,
            breakdown=breakdown,
            formatters=formatters,
        ),
    )
