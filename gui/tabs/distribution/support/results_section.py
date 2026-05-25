from __future__ import annotations

# ruff: noqa: E501
import logging
import tkinter as tk
from dataclasses import dataclass
from tkinter import ttk

from gui.i18n import tr
from gui.tooltip import Tooltip

from .formatting import _default_end, _default_start, _snapshot_values_to_display
from .results_data import (
    compose_column_meta,
    distribution_row_values_map,
    row_values_for_columns,
)

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class DistributionResultsSection:
    period_from_var: tk.StringVar
    period_to_var: tk.StringVar
    results_tree: ttk.Treeview
    status_label: ttk.Label
    fix_button: ttk.Button
    toolbar: ttk.Frame


def build_results_section(parent, *, palette) -> DistributionResultsSection:
    title_row = ttk.Frame(parent)
    title_row.grid(row=0, column=0, sticky="ew", padx=8, pady=(0, 6))
    title_row.grid_columnconfigure(0, weight=1)
    ttk.Label(
        title_row,
        text=tr("distribution.table.title", "Таблица распределения"),
        font=("Segoe UI", 11, "bold"),
    ).grid(row=0, column=0, sticky="w")

    toolbar = ttk.Frame(title_row)
    toolbar.grid(row=0, column=1, sticky="e")
    period_from_var = tk.StringVar(value=_default_start())
    period_to_var = tk.StringVar(value=_default_end())
    ttk.Label(toolbar, text=tr("common.from_short", "С:")).pack(side=tk.LEFT)
    ttk.Entry(toolbar, textvariable=period_from_var, width=9).pack(side=tk.LEFT, padx=(4, 8))
    ttk.Label(toolbar, text=tr("common.to_short", "По:")).pack(side=tk.LEFT)
    ttk.Entry(toolbar, textvariable=period_to_var, width=9).pack(side=tk.LEFT, padx=(4, 8))

    results_wrap = ttk.Frame(parent)
    results_wrap.grid(row=1, column=0, sticky="nsew", padx=8)
    results_wrap.grid_columnconfigure(0, weight=1)
    results_wrap.grid_rowconfigure(0, weight=1)

    results_tree = ttk.Treeview(
        results_wrap,
        columns=("month", "fixed", "net_income"),
        show="headings",
    )
    results_tree.grid(row=0, column=0, sticky="nsew")
    results_scroll_y = ttk.Scrollbar(results_wrap, orient="vertical", command=results_tree.yview)
    results_scroll_y.grid(row=0, column=1, sticky="ns")
    results_scroll_x = ttk.Scrollbar(results_wrap, orient="horizontal", command=results_tree.xview)
    results_scroll_x.grid(row=1, column=0, sticky="ew")
    results_tree.configure(yscrollcommand=results_scroll_y.set, xscrollcommand=results_scroll_x.set)
    results_tree.tag_configure(
        "neg_row", background=palette.danger_tint, foreground=palette.text_primary
    )
    results_tree.tag_configure(
        "odd_row", background=palette.row_alt, foreground=palette.text_primary
    )
    results_tree.tag_configure(
        "even_row", background=palette.surface_elevated, foreground=palette.text_primary
    )

    footer_row = ttk.Frame(parent)
    footer_row.grid(row=2, column=0, sticky="ew", padx=8, pady=(6, 0))
    footer_row.grid_columnconfigure(1, weight=1)
    fix_button = ttk.Button(footer_row, text=tr("distribution.fix", "Зафиксировать строку"))
    fix_button.grid(row=0, column=0, sticky="w")
    status_label = ttk.Label(footer_row, text="")
    status_label.grid(row=0, column=1, sticky="w", padx=(12, 0))
    Tooltip(
        status_label,
        tr(
            "distribution.tooltip.status",
            "Показывает видимый диапазон месяцев и количество зафиксированных строк.\n"
            "Закрытые прошлые месяцы автоматически фиксируются при запросе снимков.\n"
            "Автофиксированные строки защищены и не снимаются вручную.",
        ),
    )

    for widget in (results_tree, results_scroll_x):
        widget.bind("<Shift-MouseWheel>", _on_results_shift_mousewheel(results_tree), add="+")
        widget.bind(
            "<Shift-Button-4>",
            lambda _event: _scroll_results_horizontally(results_tree, -1, 3),
            add="+",
        )
        widget.bind(
            "<Shift-Button-5>",
            lambda _event: _scroll_results_horizontally(results_tree, 1, 3),
            add="+",
        )

    return DistributionResultsSection(
        period_from_var=period_from_var,
        period_to_var=period_to_var,
        results_tree=results_tree,
        status_label=status_label,
        fix_button=fix_button,
        toolbar=toolbar,
    )


def _accelerated_units(delta: int, *, multiplier: int = 10) -> int:
    if delta == 0:
        return 0
    base_units = max(1, abs(int(delta)) // 120)
    return base_units * multiplier


def _scroll_results_horizontally(results_tree: ttk.Treeview, direction: int, units: int) -> str:
    results_tree.xview_scroll(direction * units, "units")
    return "break"


def _on_results_shift_mousewheel(results_tree: ttk.Treeview):
    def _handler(event: tk.Event) -> str:
        delta = int(getattr(event, "delta", 0))
        units = _accelerated_units(delta)
        if units <= 0:
            return "break"
        direction = -1 if delta > 0 else 1
        return _scroll_results_horizontally(results_tree, direction, units)

    return _handler


def fit_results_columns(results_tree: ttk.Treeview, _event: tk.Event | None = None) -> None:
    column_ids = list(results_tree.cget("columns"))
    total_width = max(results_tree.winfo_width(), 0)
    if total_width <= 1 or not column_ids:
        return

    base_widths: dict[str, int] = {}
    for column_id in column_ids:
        if column_id == "month":
            base_widths[column_id] = 84
        elif column_id == "fixed":
            base_widths[column_id] = 72
        elif column_id == "net_income":
            base_widths[column_id] = 130
        elif column_id.startswith("sub_"):
            base_widths[column_id] = 92
        else:
            base_widths[column_id] = 96

    if len(column_ids) == 1:
        results_tree.column(column_ids[0], width=max(total_width - 6, 80), stretch=False)
        return

    slack = 6
    trailing_id = column_ids[-1]
    fixed_total = sum(base_widths[column_id] for column_id in column_ids[:-1])
    trailing_width = max(base_widths[trailing_id], total_width - fixed_total - slack)

    for column_id in column_ids[:-1]:
        results_tree.column(column_id, width=base_widths[column_id], stretch=False)
    results_tree.column(trailing_id, width=trailing_width, stretch=False)


def configure_results_columns(
    results_tree: ttk.Treeview, column_ids: list[str], headings: dict[str, str]
) -> None:
    results_tree.configure(columns=column_ids, displaycolumns=column_ids)
    for column_id in column_ids:
        is_month = column_id == "month"
        is_sub = column_id.startswith("sub_")
        is_fixed = column_id == "fixed"
        width = 92 if is_sub else (60 if is_month else (50 if is_fixed else 90))
        anchor = "center" if is_fixed else ("w" if is_month else "e")
        results_tree.heading(column_id, text=headings[column_id])
        results_tree.column(column_id, width=width, anchor=anchor, stretch=False)
    fit_results_columns(results_tree)


def selected_result_month(results_tree: ttk.Treeview) -> str | None:
    selection = results_tree.selection()
    if not selection:
        return None
    return selection[0]


def update_fix_button_state(
    context, section: DistributionResultsSection, _event: tk.Event | None = None
) -> None:
    month = selected_result_month(section.results_tree)
    if month is None:
        section.fix_button.configure(
            text=tr("distribution.fix", "Зафиксировать строку"), state=tk.DISABLED
        )
        return
    if context.controller.is_distribution_month_auto_fixed(month):
        section.fix_button.configure(
            text=tr("distribution.auto_fixed", "Автофикс"), state=tk.DISABLED
        )
        return
    button_text = (
        tr("distribution.unfix", "Снять фиксацию")
        if context.controller.is_distribution_month_fixed(month)
        else tr("distribution.fix", "Зафиксировать строку")
    )
    section.fix_button.configure(text=button_text, state=tk.NORMAL)


def refresh_results(
    context, section: DistributionResultsSection, *, palette, format_display_amount
) -> None:
    start_month = (section.period_from_var.get() or "").strip() or _default_start()
    end_month = (section.period_to_var.get() or "").strip() or _default_end()

    try:
        items = context.controller.get_distribution_items()
        history = context.controller.get_distribution_history(start_month, end_month)
        visible_fixed_rows = context.controller.get_frozen_distribution_rows(start_month, end_month)
    except (ValueError, TypeError, RuntimeError, tk.TclError) as exc:
        logger.warning("Failed to refresh distribution results: %s", exc)
        section.status_label.config(text=str(exc), foreground=palette.danger)
        section.results_tree.delete(*section.results_tree.get_children())
        return

    live_history_by_month = {distribution.month: distribution for distribution in history}
    visible_fixed_rows_by_month = {row.month: row for row in visible_fixed_rows}
    visible_months = sorted(set(live_history_by_month) | set(visible_fixed_rows_by_month))

    if not items and not visible_fixed_rows:
        section.results_tree.delete(*section.results_tree.get_children())
        section.results_tree.configure(
            columns=("month", "fixed", "net_income"),
            displaycolumns=("month", "fixed", "net_income"),
        )
        section.results_tree.heading("month", text=tr("common.month", "Месяц"))
        section.results_tree.heading("fixed", text=tr("distribution.fixed", "Фиксация"))
        section.results_tree.heading(
            "net_income", text=tr("distribution.net_income", "Чистый доход")
        )
        section.results_tree.column("month", width=80, minwidth=80, anchor="w", stretch=False)
        section.results_tree.column("fixed", width=80, minwidth=80, anchor="center", stretch=False)
        section.results_tree.column(
            "net_income", width=130, minwidth=130, anchor="e", stretch=False
        )
        fit_results_columns(section.results_tree)
        section.status_label.config(
            text=tr(
                "distribution.empty",
                "Элементов распределения пока нет. Добавьте структуру слева, чтобы заполнить таблицу.",
            ),
            foreground="",
        )
        section.fix_button.configure(
            state=tk.DISABLED, text=tr("distribution.fix", "Зафиксировать строку")
        )
        return

    column_ids, headings = compose_column_meta(context, items, visible_fixed_rows)
    configure_results_columns(section.results_tree, column_ids, headings)
    section.results_tree.delete(*section.results_tree.get_children())
    for index, month in enumerate(visible_months):
        frozen_row = visible_fixed_rows_by_month.get(month)
        live_distribution = live_history_by_month.get(month)
        if frozen_row is not None:
            is_negative = frozen_row.is_negative
            values_by_column = _snapshot_values_to_display(
                frozen_row.values_by_column,
                format_display_amount=format_display_amount,
            )
        elif live_distribution is not None:
            is_negative = live_distribution.is_negative
            values_by_column = distribution_row_values_map(
                context,
                live_distribution,
                items,
                format_display_amount=format_display_amount,
            )
        else:
            continue

        values_by_column["month"] = month
        values_by_column["fixed"] = "✓" if frozen_row is not None else ""
        tag = "neg_row" if is_negative else ("odd_row" if index % 2 == 0 else "even_row")
        section.results_tree.insert(
            "",
            "end",
            iid=month,
            values=row_values_for_columns(column_ids, values_by_column),
            tags=(tag,),
        )

    fixed_count = sum(1 for row in visible_fixed_rows if row.month in visible_months)
    status_text = tr(
        "distribution.status.range",
        "Показано месяцев: {count}, период {start} — {end}",
        count=len(visible_months),
        start=start_month,
        end=end_month,
    )
    if fixed_count:
        status_text += tr(
            "distribution.status.fixed", " | зафиксировано: {count}", count=fixed_count
        )
    section.status_label.config(text=f"{status_text} ⓘ", foreground="")
    update_fix_button_state(context, section)
