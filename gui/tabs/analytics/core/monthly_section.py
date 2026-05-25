from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from tkinter import ttk

from gui.i18n import tr
from gui.ui_helpers import attach_treeview_scrollbars
from gui.ui_theme import create_card_section, enable_treeview_zebra


@dataclass(slots=True)
class AnalyticsTimelineSection:
    timeline_canvas: tk.Canvas


@dataclass(slots=True)
class AnalyticsMonthlySection:
    monthly_tree: ttk.Treeview


def build_timeline_section(parent, *, palette) -> AnalyticsTimelineSection:
    timeline_card = create_card_section(parent, tr("analytics.timeline", "Динамика капитала"))
    timeline_card.grid(row=1, column=1, sticky="nsew", padx=(6, 16), pady=(6, 16))
    timeline_frame = timeline_card.winfo_children()[-1]
    timeline_frame.grid_columnconfigure(0, weight=1)
    timeline_frame.grid_rowconfigure(0, weight=1)
    timeline_canvas = tk.Canvas(
        timeline_frame,
        height=180,
        bg=palette.surface_elevated,
        highlightthickness=0,
    )
    timeline_canvas.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
    return AnalyticsTimelineSection(timeline_canvas=timeline_canvas)


def build_monthly_section(parent, *, palette) -> AnalyticsMonthlySection:
    monthly_card = create_card_section(parent, tr("analytics.monthly_report", "Помесячный отчет"))
    monthly_card.grid(row=2, column=1, sticky="nsew", padx=(6, 16), pady=(0, 16))
    monthly_frame = monthly_card.winfo_children()[-1]
    monthly_frame.grid_columnconfigure(0, weight=1)
    monthly_frame.grid_rowconfigure(0, weight=1)

    monthly_tree = ttk.Treeview(
        monthly_frame,
        columns=("month", "income", "expenses", "cashflow", "savings"),
        show="headings",
        height=10,
    )
    enable_treeview_zebra(monthly_tree)
    monthly_tree.grid(row=0, column=0, sticky="nsew")
    monthly_tree.heading("month", text=tr("common.month", "Месяц"))
    monthly_tree.heading("income", text=tr("analytics.income", "Доходы"))
    monthly_tree.heading("expenses", text=tr("analytics.expenses", "Расходы"))
    monthly_tree.heading("cashflow", text=tr("analytics.cashflow", "Денежный поток"))
    monthly_tree.heading("savings", text=tr("analytics.savings_pct", "Сбережения %"))
    monthly_tree.column("month", width=80, minwidth=80)
    monthly_tree.column("income", width=100, minwidth=100, anchor="e")
    monthly_tree.column("expenses", width=100, minwidth=100, anchor="e")
    monthly_tree.column("cashflow", width=120, minwidth=120, anchor="e")
    monthly_tree.column("savings", width=90, minwidth=90, anchor="e")
    monthly_tree.tag_configure("positive", foreground=palette.chart_income)
    monthly_tree.tag_configure("negative", foreground=palette.chart_expense)
    attach_treeview_scrollbars(monthly_frame, monthly_tree, row=0, column=0, horizontal=True)
    return AnalyticsMonthlySection(monthly_tree=monthly_tree)
