from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk
from types import SimpleNamespace
from typing import cast

from domain.records import ExpenseRecord
from gui.tabs.infographics_tab import (
    _legend_category_max_width,
    draw_expense_pie,
    update_pie_month_options,
)
from gui.ui_theme import get_palette


def test_update_pie_month_options_defaults_to_all_time() -> None:
    root = tk.Tk()
    root.withdraw()
    try:
        var = tk.StringVar(master=root, value="")
        combo = ttk.Combobox(root, textvariable=var)
        records = [SimpleNamespace(date="2026-05-09")]

        update_pie_month_options(combo, var, records)

        assert combo["values"][0] == "Все время"
        assert var.get() == "Все время"
    finally:
        root.destroy()


def test_draw_expense_pie_renders_canvas_and_legend() -> None:
    root = tk.Tk()
    root.withdraw()
    try:
        pie_var = tk.StringVar(master=root, value="Все время")
        pie_canvas = tk.Canvas(root, width=220, height=220)
        legend_canvas = tk.Canvas(root, width=160, height=220)
        legend_frame = tk.Frame(root)
        pie_canvas.pack()
        legend_canvas.pack()
        legend_frame.pack()
        root.update_idletasks()

        records = [
            ExpenseRecord(
                id=1,
                date="2026-05-09",
                wallet_id=1,
                amount_original=250.0,
                currency="KZT",
                rate_at_operation=1.0,
                amount_base=250.0,
                category="Food",
            )
        ]

        draw_expense_pie(
            pie_month_var=pie_var,
            expense_pie_canvas=pie_canvas,
            expense_legend_canvas=legend_canvas,
            expense_legend_frame=legend_frame,
            records=records,
        )

        assert pie_canvas.find_all()
        assert legend_frame.winfo_children()
        legend_row = legend_frame.winfo_children()[0]
        legend_widgets = legend_row.winfo_children()
        assert len(legend_widgets) == 3
        assert legend_widgets[1].cget("text") == "Food"
        assert legend_widgets[2].cget("text") == "250.00"
    finally:
        root.destroy()


def test_draw_expense_pie_colors_grouped_other_slice_gray() -> None:
    root = tk.Tk()
    root.withdraw()
    try:
        pie_var = tk.StringVar(master=root, value="Все время")
        pie_canvas = tk.Canvas(root, width=220, height=220)
        legend_canvas = tk.Canvas(root, width=160, height=220)
        legend_frame = tk.Frame(root)
        pie_canvas.pack()
        legend_canvas.pack()
        legend_frame.pack()
        root.update_idletasks()

        records = [
            ExpenseRecord(
                id=index,
                date="2026-05-09",
                wallet_id=1,
                amount_original=float(100 - index),
                currency="KZT",
                rate_at_operation=1.0,
                amount_base=float(100 - index),
                category=f"Category {index}",
            )
            for index in range(1, 12)
        ]

        draw_expense_pie(
            pie_month_var=pie_var,
            expense_pie_canvas=pie_canvas,
            expense_legend_canvas=legend_canvas,
            expense_legend_frame=legend_frame,
            records=records,
        )

        other_row = legend_frame.winfo_children()[-1]
        color_box = cast(tk.Canvas, other_row.winfo_children()[0])
        rect_id = color_box.find_all()[0]
        assert color_box.itemcget(rect_id, "fill") == get_palette().chart_empty
    finally:
        root.destroy()


def test_legend_category_width_uses_actual_amount_text_width() -> None:
    class _MeasuredFont:
        def measure(self, text: str) -> int:
            return len(text) * 6

    amount_font = cast(tkfont.Font, _MeasuredFont())

    normal_amount_width = _legend_category_max_width(
        canvas_width=220,
        amount_text="140,000.00 KZT",
        amount_font=amount_font,
    )
    long_amount_width = _legend_category_max_width(
        canvas_width=220,
        amount_text="9,999,999.99 KZT",
        amount_font=amount_font,
    )

    assert normal_amount_width > 72
    assert long_amount_width < normal_amount_width
