"""Infographics tab builder."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk

from gui.combobox_compat import enable_wayland_combobox_support
from gui.i18n import tr
from gui.ui_theme import PAD_LG, PAD_SM, PAD_XL, create_card_section, get_palette

from .contracts import AfterLike, InfographicsTabBindings


def build_infographics_tab(
    parent: tk.Frame | ttk.Frame,
    *,
    on_chart_filter_change: Callable[..., None],
    on_refresh_charts: Callable[[], None],
    on_legend_mousewheel: Callable[[tk.Event], None],
    after: AfterLike,
    after_cancel: Callable[[str], None],
) -> InfographicsTabBindings:
    palette = get_palette()
    parent.grid_columnconfigure(0, weight=1, uniform="infographics_top")
    parent.grid_columnconfigure(1, weight=1, uniform="infographics_top")
    parent.grid_rowconfigure(1, weight=1)
    parent.grid_rowconfigure(2, weight=1)

    pie_card = create_card_section(
        parent, tr("infographics.expenses_by_category", "Расходы по категориям")
    )
    pie_card.grid(row=1, column=0, sticky="nsew", padx=(PAD_XL, PAD_SM), pady=PAD_LG)
    pie_frame = pie_card.winfo_children()[-1]
    pie_frame.grid_columnconfigure(0, weight=2)
    pie_frame.grid_columnconfigure(1, weight=1)
    pie_frame.grid_rowconfigure(1, weight=1)

    pie_controls = ttk.Frame(pie_frame, style="CardBody.TFrame")
    pie_controls.grid(row=0, column=0, columnspan=2, sticky="ew", padx=10, pady=(8, 0))
    pie_controls.grid_columnconfigure(1, weight=1)
    ttk.Label(
        pie_controls,
        text=tr("infographics.month", "Месяц:"),
        style="FormField.TLabel",
    ).grid(row=0, column=0, sticky="w")

    pie_month_var = tk.StringVar()
    pie_month_menu = ttk.Combobox(
        pie_controls,
        textvariable=pie_month_var,
        values=[],
        state="readonly",
    )
    pie_month_menu.grid(row=0, column=1, sticky="w", padx=(6, 0))
    enable_wayland_combobox_support(pie_month_menu)
    pie_month_var.trace_add("write", on_chart_filter_change)

    daily_card = create_card_section(
        parent, tr("infographics.daily_cashflow", "Доходы и расходы по дням месяца")
    )
    daily_card.grid(row=1, column=1, sticky="nsew", padx=(PAD_SM, PAD_XL), pady=PAD_LG)
    daily_frame = daily_card.winfo_children()[-1]
    daily_frame.grid_columnconfigure(0, weight=1)
    daily_frame.grid_rowconfigure(1, weight=1)

    monthly_card = create_card_section(
        parent, tr("infographics.monthly_cashflow", "Доходы и расходы по месяцам года")
    )
    monthly_card.grid(row=2, column=0, columnspan=2, sticky="nsew", padx=PAD_XL, pady=(0, PAD_LG))
    monthly_frame = monthly_card.winfo_children()[-1]
    monthly_frame.grid_columnconfigure(0, weight=1)
    monthly_frame.grid_rowconfigure(1, weight=1)

    expense_pie_canvas = tk.Canvas(
        pie_frame,
        height=240,
        bg=palette.surface_elevated,
        highlightthickness=0,
    )
    expense_pie_canvas.grid(row=1, column=0, sticky="nsew", padx=(10, 4), pady=10)

    legend_container = ttk.Frame(pie_frame)
    legend_container.grid(row=1, column=1, sticky="nsew", padx=(4, 10), pady=10)
    legend_container.grid_columnconfigure(0, weight=1)
    legend_container.grid_rowconfigure(0, weight=1)
    expense_legend_canvas = tk.Canvas(
        legend_container,
        height=240,
        highlightthickness=0,
        bg=palette.surface_elevated,
    )
    expense_legend_canvas.grid(row=0, column=0, sticky="nsew")
    legend_scroll = ttk.Scrollbar(
        legend_container,
        orient="vertical",
        command=expense_legend_canvas.yview,
    )
    legend_scroll.grid(row=0, column=1, sticky="ns")
    expense_legend_canvas.configure(yscrollcommand=legend_scroll.set)

    expense_legend_frame = tk.Frame(expense_legend_canvas, bg=palette.surface_elevated)
    expense_legend_canvas.create_window(
        (0, 0),
        window=expense_legend_frame,
        anchor="nw",
        tags=("legend_window",),
    )

    def _update_legend_scroll(_event: object | None = None) -> None:
        expense_legend_canvas.configure(scrollregion=expense_legend_canvas.bbox("all"))
        bbox = expense_legend_canvas.bbox("all")
        if bbox:
            width = max(expense_legend_canvas.winfo_width(), bbox[2] - bbox[0])
            expense_legend_canvas.itemconfigure("legend_window", width=max(width - 10, 0))

    expense_legend_frame.bind("<Configure>", _update_legend_scroll)
    expense_legend_canvas.bind("<Configure>", _update_legend_scroll)
    expense_legend_canvas.bind("<MouseWheel>", on_legend_mousewheel)
    expense_legend_frame.bind("<MouseWheel>", on_legend_mousewheel)

    daily_controls = ttk.Frame(daily_frame, style="CardBody.TFrame")
    daily_controls.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 0))
    daily_controls.grid_columnconfigure(1, weight=1)
    ttk.Label(
        daily_controls,
        text=tr("infographics.month", "Месяц:"),
        style="FormField.TLabel",
    ).grid(row=0, column=0, sticky="w")

    chart_month_var = tk.StringVar()
    chart_month_menu = ttk.Combobox(
        daily_controls,
        textvariable=chart_month_var,
        values=[],
        state="readonly",
    )
    chart_month_menu.grid(row=0, column=1, sticky="w", padx=(6, 0))
    enable_wayland_combobox_support(chart_month_menu)
    chart_month_var.trace_add("write", on_chart_filter_change)

    daily_bar_canvas = tk.Canvas(
        daily_frame,
        height=220,
        bg=palette.surface_elevated,
        highlightthickness=0,
    )
    daily_bar_canvas.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)

    monthly_controls = ttk.Frame(monthly_frame, style="CardBody.TFrame")
    monthly_controls.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 0))
    monthly_controls.grid_columnconfigure(1, weight=1)
    ttk.Label(
        monthly_controls,
        text=tr("infographics.year", "Год:"),
        style="FormField.TLabel",
    ).grid(row=0, column=0, sticky="w")

    chart_year_var = tk.StringVar()
    chart_year_menu = ttk.Combobox(
        monthly_controls,
        textvariable=chart_year_var,
        values=[],
        state="readonly",
    )
    chart_year_menu.grid(row=0, column=1, sticky="w", padx=(6, 0))
    enable_wayland_combobox_support(chart_year_menu)
    chart_year_var.trace_add("write", on_chart_filter_change)

    monthly_bar_canvas = tk.Canvas(
        monthly_frame,
        height=220,
        bg=palette.surface_elevated,
        highlightthickness=0,
    )
    monthly_bar_canvas.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)

    chart_redraw_job: str | None = None

    def _schedule_redraw(_event: object | None = None) -> None:
        nonlocal chart_redraw_job
        if chart_redraw_job is not None:
            try:
                after_cancel(chart_redraw_job)
            except (tk.TclError, RuntimeError):
                pass
        chart_redraw_job = after(120, on_refresh_charts)

    expense_pie_canvas.bind("<Configure>", _schedule_redraw)
    daily_bar_canvas.bind("<Configure>", _schedule_redraw)
    monthly_bar_canvas.bind("<Configure>", _schedule_redraw)

    return InfographicsTabBindings(
        pie_month_var=pie_month_var,
        pie_month_menu=pie_month_menu,
        chart_month_var=chart_month_var,
        chart_month_menu=chart_month_menu,
        chart_year_var=chart_year_var,
        chart_year_menu=chart_year_menu,
        expense_pie_canvas=expense_pie_canvas,
        expense_legend_canvas=expense_legend_canvas,
        expense_legend_frame=expense_legend_frame,
        daily_bar_canvas=daily_bar_canvas,
        monthly_bar_canvas=monthly_bar_canvas,
    )
