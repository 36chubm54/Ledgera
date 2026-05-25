"""Analytics tab builder."""

from __future__ import annotations

import tkinter as tk
from datetime import datetime
from tkinter import ttk

from gui.i18n import tr
from gui.ui_theme import PAD_LG, PAD_SM, PAD_XL, get_palette

from ..support.refresh_support import (
    AnalyticsRefreshState,
    build_display_formatters,
    schedule_analytics_redraw,
)
from .breakdown_section import build_breakdown_section
from .contracts import AnalyticsTabBindings, AnalyticsTabContext
from .monthly_section import build_monthly_section, build_timeline_section
from .refresh import refresh_analytics
from .summary_section import build_summary_section


def build_analytics_tab(
    parent: tk.Frame | ttk.Frame,
    context: AnalyticsTabContext,
) -> AnalyticsTabBindings:
    palette = get_palette()
    parent.grid_columnconfigure(0, weight=1, uniform="analytics_columns")
    parent.grid_columnconfigure(1, weight=1, uniform="analytics_columns")
    parent.grid_rowconfigure(1, weight=1)
    parent.grid_rowconfigure(2, weight=2)

    top = ttk.Frame(parent)
    top.grid(row=0, column=0, columnspan=2, sticky="ew", padx=PAD_XL, pady=(PAD_LG, PAD_SM))
    top.grid_columnconfigure(5, weight=1)

    ttk.Label(top, text=tr("analytics.from", "С даты:")).grid(row=0, column=0, sticky="w")
    period_from_entry = ttk.Entry(top, width=12)
    period_from_entry.grid(row=0, column=1, sticky="w", padx=(6, 14))

    ttk.Label(top, text=tr("analytics.to", "По дату:")).grid(row=0, column=2, sticky="w")
    period_to_entry = ttk.Entry(top, width=12)
    period_to_entry.grid(row=0, column=3, sticky="w", padx=(6, 14))

    refresh_button = ttk.Button(top, text=tr("analytics.refresh", "Обновить"))
    refresh_button.grid(row=0, column=4, sticky="w")

    breakdown_by_tags_var = tk.BooleanVar(value=False)
    breakdown_by_tags_check = ttk.Checkbutton(
        top,
        text=tr("analytics.breakdown_by_tags", "Разбивка по тегам"),
        variable=breakdown_by_tags_var,
    )
    breakdown_by_tags_check.grid(row=0, column=5, sticky="e")

    default_start = datetime.now().strftime("%Y-01-01")
    default_end = datetime.now().strftime("%Y-%m-%d")
    period_from_entry.insert(0, default_start)
    period_to_entry.insert(0, default_end)

    summary = build_summary_section(parent, palette=palette)
    breakdown = build_breakdown_section(parent, palette=palette)
    timeline = build_timeline_section(parent, palette=palette)
    monthly = build_monthly_section(parent, palette=palette)

    formatters = build_display_formatters(context)
    refresh_state = AnalyticsRefreshState()

    def _refresh_analytics() -> None:
        refresh_analytics(
            context=context,
            summary=summary,
            breakdown=breakdown,
            timeline=timeline,
            monthly=monthly,
            breakdown_by_tags_var=breakdown_by_tags_var,
            period_from_text=period_from_entry.get(),
            period_to_text=period_to_entry.get(),
            default_start=default_start,
            default_end=default_end,
            palette=palette,
            formatters=formatters,
            state=refresh_state,
        )

    refresh_button.configure(command=_refresh_analytics)
    breakdown_by_tags_check.configure(command=_refresh_analytics)

    def _toggle_tag_mode() -> None:
        breakdown_by_tags_var.set(not bool(breakdown_by_tags_var.get()))
        _refresh_analytics()

    def _bind_enter_refresh(entry: ttk.Entry) -> None:
        entry.bind("<Return>", lambda _event: _refresh_analytics())

    _bind_enter_refresh(period_from_entry)
    _bind_enter_refresh(period_to_entry)

    timeline.timeline_canvas.bind(
        "<Configure>",
        lambda _event: schedule_analytics_redraw(
            context=context,
            state=refresh_state,
            timeline=timeline,
            breakdown=breakdown,
            formatters=formatters,
        ),
    )
    breakdown.category_canvas.bind(
        "<Configure>",
        lambda _event: schedule_analytics_redraw(
            context=context,
            state=refresh_state,
            timeline=timeline,
            breakdown=breakdown,
            formatters=formatters,
        ),
    )

    _refresh_analytics()

    return AnalyticsTabBindings(
        period_from_entry=period_from_entry,
        period_to_entry=period_to_entry,
        net_worth_label=summary.net_worth_label,
        savings_rate_label=summary.savings_rate_label,
        burn_rate_label=summary.burn_rate_label,
        spending_tree=breakdown.spending_tree,
        income_tree=breakdown.income_tree,
        category_canvas=breakdown.category_canvas,
        monthly_tree=monthly.monthly_tree,
        timeline_canvas=timeline.timeline_canvas,
        refresh=_refresh_analytics,
        toggle_tag_mode=_toggle_tag_mode,
    )
