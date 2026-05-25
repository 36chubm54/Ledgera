from __future__ import annotations

# ruff: noqa: E501
import tkinter as tk
from dataclasses import dataclass
from tkinter import ttk
from typing import cast

from gui.i18n import tr
from gui.ui_helpers import attach_treeview_scrollbars, enable_treeview_column_autosize
from gui.ui_theme import create_card_section, enable_treeview_zebra


@dataclass(slots=True)
class AnalyticsBreakdownSection:
    title_label: ttk.Label
    category_breakdown_frame: ttk.Frame
    tag_breakdown_frame: ttk.Frame
    spending_tree: ttk.Treeview
    income_tree: ttk.Treeview
    tag_tree: ttk.Treeview
    category_canvas: tk.Canvas


def build_breakdown_section(parent, *, palette) -> AnalyticsBreakdownSection:
    breakdown_card = create_card_section(
        parent, tr("analytics.breakdown", "Разбивка по категориям")
    )
    breakdown_card.grid(row=2, column=0, sticky="nsew", padx=(16, 6), pady=(0, 16))
    breakdown_frame = cast(ttk.Frame, breakdown_card.winfo_children()[-1])
    breakdown_title_label = cast(ttk.Label, breakdown_card.winfo_children()[0])
    breakdown_frame.grid_columnconfigure(0, weight=3)
    breakdown_frame.grid_columnconfigure(1, weight=2, minsize=240)
    breakdown_frame.grid_rowconfigure(0, weight=1)

    breakdown_left = ttk.Frame(breakdown_frame, padding=(10, 10))
    breakdown_left.grid(row=0, column=0, sticky="nsew")
    breakdown_left.grid_columnconfigure(0, weight=1)

    category_breakdown_frame = ttk.Frame(breakdown_left)
    category_breakdown_frame.grid(row=0, column=0, sticky="nsew")
    category_breakdown_frame.grid_columnconfigure(0, weight=1)

    ttk.Label(
        category_breakdown_frame,
        text=tr("analytics.expenses", "Расходы"),
        font=("Segoe UI", 10, "bold"),
    ).grid(row=0, column=0, sticky="w")
    spending_tree = ttk.Treeview(
        category_breakdown_frame,
        columns=("category", "total", "count"),
        show="headings",
        height=4,
    )
    enable_treeview_zebra(spending_tree)
    spending_tree.grid(row=1, column=0, sticky="nsew", pady=(6, 14))
    spending_tree.heading("category", text=tr("analytics.category", "Категория"))
    spending_tree.heading("total", text=tr("common.amount_short", "Сумма"))
    spending_tree.heading("count", text=tr("common.count_short", "#"))
    spending_tree.column("category", width=200, minwidth=200)
    spending_tree.column("total", width=120, minwidth=120, anchor="e")
    spending_tree.column("count", width=60, minwidth=60, anchor="center")
    enable_treeview_column_autosize(spending_tree, columns=("category",), max_width=360)
    attach_treeview_scrollbars(
        category_breakdown_frame, spending_tree, row=1, column=0, horizontal=False, pady=0
    )

    ttk.Label(
        category_breakdown_frame,
        text=tr("analytics.income", "Доходы"),
        font=("Segoe UI", 10, "bold"),
    ).grid(row=2, column=0, sticky="w")
    income_tree = ttk.Treeview(
        category_breakdown_frame,
        columns=("category", "total", "count"),
        show="headings",
        height=4,
    )
    enable_treeview_zebra(income_tree)
    income_tree.grid(row=3, column=0, sticky="nsew", pady=(6, 0))
    income_tree.heading("category", text=tr("analytics.category", "Категория"))
    income_tree.heading("total", text=tr("common.amount_short", "Сумма"))
    income_tree.heading("count", text=tr("common.count_short", "#"))
    income_tree.column("category", width=200, minwidth=200)
    income_tree.column("total", width=120, minwidth=120, anchor="e")
    income_tree.column("count", width=60, minwidth=60, anchor="center")
    enable_treeview_column_autosize(income_tree, columns=("category",), max_width=360)
    attach_treeview_scrollbars(
        category_breakdown_frame, income_tree, row=3, column=0, horizontal=False, pady=0
    )

    tag_breakdown_frame = ttk.Frame(breakdown_left)
    tag_breakdown_frame.grid(row=0, column=0, sticky="nsew")
    tag_breakdown_frame.grid_columnconfigure(0, weight=1)
    tag_breakdown_frame.grid_rowconfigure(1, weight=1)

    ttk.Label(
        tag_breakdown_frame,
        text=tr("analytics.tags_expenses", "Теги расходов"),
        font=("Segoe UI", 10, "bold"),
    ).grid(row=0, column=0, sticky="w")
    tag_tree = ttk.Treeview(
        tag_breakdown_frame,
        columns=("tag", "total", "count"),
        show="headings",
        height=9,
    )
    enable_treeview_zebra(tag_tree)
    tag_tree.grid(row=1, column=0, sticky="nsew", pady=(6, 0))
    tag_tree.heading("tag", text=tr("common.tags_short", "Теги"))
    tag_tree.heading("total", text=tr("common.amount_short", "Сумма"))
    tag_tree.heading("count", text=tr("common.count_short", "#"))
    tag_tree.column("tag", width=100, minwidth=100)
    tag_tree.column("total", width=90, minwidth=90, anchor="e")
    tag_tree.column("count", width=50, minwidth=50, anchor="center")
    enable_treeview_column_autosize(tag_tree, columns=("tag",), max_width=320)
    attach_treeview_scrollbars(
        tag_breakdown_frame, tag_tree, row=1, column=0, horizontal=False, pady=0
    )
    ttk.Label(
        tag_breakdown_frame,
        text=tr(
            "analytics.tags_split_hint",
            "Суммы по тегам не складываются в общий итог: одна запись может одновременно входить в несколько тегов.",
        ),
    ).grid(row=2, column=0, sticky="w", pady=(8, 0))
    tag_breakdown_frame.grid_remove()

    breakdown_right = ttk.Frame(breakdown_frame, padding=(0, 10, 10, 10))
    breakdown_right.grid(row=0, column=1, sticky="nsew")
    breakdown_right.grid_propagate(False)
    breakdown_right.grid_columnconfigure(0, weight=1)
    breakdown_right.grid_rowconfigure(0, weight=1)
    category_canvas = tk.Canvas(
        breakdown_right,
        width=220,
        height=220,
        bg=palette.surface_elevated,
        highlightthickness=0,
    )
    category_canvas.grid(row=0, column=0, sticky="nsew")

    return AnalyticsBreakdownSection(
        title_label=breakdown_title_label,
        category_breakdown_frame=category_breakdown_frame,
        tag_breakdown_frame=tag_breakdown_frame,
        spending_tree=spending_tree,
        income_tree=income_tree,
        tag_tree=tag_tree,
        category_canvas=category_canvas,
    )


def apply_breakdown_mode(section: AnalyticsBreakdownSection, *, is_tags_mode: bool) -> None:
    if is_tags_mode:
        section.category_canvas.configure(width=220, height=220)
        section.category_breakdown_frame.grid_remove()
        section.tag_breakdown_frame.grid()
        section.title_label.configure(
            text=tr("analytics.breakdown_tags", "Покрытие расходов тегами")
        )
    else:
        section.category_canvas.configure(width=220, height=220)
        section.tag_breakdown_frame.grid_remove()
        section.category_breakdown_frame.grid()
        section.title_label.configure(text=tr("analytics.breakdown", "Разбивка по категориям"))
