"""Distribution tab - structure editor and monthly distribution table."""

from __future__ import annotations

import logging
import tkinter as tk
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date as dt_date
from tkinter import ttk
from typing import Any, Protocol

from domain.distribution import DistributionItem, FrozenDistributionRow, MonthlyDistribution
from gui.i18n import tr
from gui.tooltip import Tooltip
from gui.ui_dialogs import messagebox_compat as messagebox
from gui.ui_helpers import ask_numeric_text, ask_text
from gui.ui_theme import get_palette

logger = logging.getLogger(__name__)


def _parse_snapshot_amount(value_text: str) -> float | None:
    text = str(value_text or "").strip()
    if not text or text == "-":
        return None
    normalized = text.replace(" ", "").replace(",", "")
    try:
        return float(normalized)
    except ValueError:
        return None


def _snapshot_values_to_display(
    values_by_column: dict[str, str],
    *,
    format_display_amount: Callable[[float, int], str],
) -> dict[str, str]:
    display_values = dict(values_by_column)
    for column_id, value_text in tuple(display_values.items()):
        if column_id in {"month", "fixed"}:
            continue
        if not (
            column_id == "net_income"
            or column_id.startswith("item_")
            or column_id.startswith("sub_")
        ):
            continue
        amount_base = _parse_snapshot_amount(value_text)
        if amount_base is None:
            continue
        display_values[column_id] = format_display_amount(amount_base, 2)
    return display_values


class DistributionTabContext(Protocol):
    controller: Any


@dataclass(slots=True)
class DistributionTabBindings:
    structure_tree: ttk.Treeview
    validation_label: ttk.Label
    period_from_var: tk.StringVar
    period_to_var: tk.StringVar
    results_tree: ttk.Treeview
    status_label: ttk.Label
    refresh: Callable[[], None]


def build_distribution_tab(
    parent: tk.Frame | ttk.Frame,
    *,
    context: DistributionTabContext,
) -> DistributionTabBindings:
    palette = get_palette()

    def format_display_amount(amount: float, precision: int = 2) -> str:
        return context.controller.format_display_amount(amount, precision=precision)

    parent.grid_columnconfigure(0, weight=1)
    parent.grid_rowconfigure(0, weight=1)

    content = ttk.Frame(parent)
    content.grid(row=0, column=0, sticky="nsew", padx=10, pady=8)
    content.grid_columnconfigure(0, minsize=400, weight=0)
    content.grid_columnconfigure(1, weight=1)
    content.grid_rowconfigure(0, weight=1)

    left_frame = ttk.Frame(content, width=400, padding=(0, 0, 8, 0))
    left_frame.grid(row=0, column=0, sticky="nsew")
    left_frame.grid_columnconfigure(0, weight=1)
    left_frame.grid_rowconfigure(1, weight=1)

    right_frame = ttk.Frame(content)
    right_frame.grid(row=0, column=1, sticky="nsew")
    right_frame.grid_columnconfigure(0, weight=1)
    right_frame.grid_rowconfigure(1, weight=1)

    ttk.Label(
        left_frame,
        text=tr("distribution.structure.title", "Структура распределения"),
        font=("Segoe UI", 11, "bold"),
    ).grid(row=0, column=0, sticky="w", padx=8, pady=(0, 6))

    structure_wrap = ttk.Frame(left_frame)
    structure_wrap.grid(row=1, column=0, sticky="nsew", padx=8)
    structure_wrap.grid_columnconfigure(0, weight=1)
    structure_wrap.grid_rowconfigure(0, weight=1)

    structure_tree = ttk.Treeview(
        structure_wrap,
        columns=("pct", "group"),
        show="tree headings",
        height=18,
    )
    structure_tree.heading("#0", text=tr("common.name", "Название"))
    structure_tree.heading("pct", text="%")
    structure_tree.heading("group", text=tr("common.group", "Группа"))
    structure_tree.column("#0", width=240, anchor="w", stretch=False)
    structure_tree.column("pct", width=70, anchor="center", stretch=False)
    structure_tree.column("group", width=180, minwidth=160, anchor="w", stretch=True)
    structure_tree.tag_configure(
        "group_header",
        foreground=palette.accent_blue,
        font=("Segoe UI", 9, "bold"),
    )
    structure_tree.tag_configure("item", foreground=palette.text_primary)
    structure_tree.tag_configure("subitem", foreground=palette.accent_blue)
    structure_tree.grid(row=0, column=0, sticky="nsew")

    structure_scroll = ttk.Scrollbar(
        structure_wrap,
        orient="vertical",
        command=structure_tree.yview,
    )
    structure_scroll.grid(row=0, column=1, sticky="ns")
    structure_tree.configure(yscrollcommand=structure_scroll.set)

    validation_label = ttk.Label(left_frame, text="", justify=tk.LEFT)
    validation_label.grid(row=2, column=0, sticky="w", padx=8, pady=(6, 2))

    buttons = ttk.Frame(left_frame)
    buttons.grid(row=3, column=0, sticky="w", padx=8, pady=(4, 0))

    title_row = ttk.Frame(right_frame)
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

    results_wrap = ttk.Frame(right_frame)
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
    results_scroll_x = ttk.Scrollbar(
        results_wrap,
        orient="horizontal",
        command=results_tree.xview,
    )
    results_scroll_x.grid(row=1, column=0, sticky="ew")
    results_tree.configure(
        yscrollcommand=results_scroll_y.set,
        xscrollcommand=results_scroll_x.set,
    )
    results_tree.tag_configure(
        "neg_row",
        background=palette.danger_tint,
        foreground=palette.text_primary,
    )
    results_tree.tag_configure(
        "odd_row",
        background=palette.row_alt,
        foreground=palette.text_primary,
    )
    results_tree.tag_configure(
        "even_row",
        background=palette.surface_elevated,
        foreground=palette.text_primary,
    )

    footer_row = ttk.Frame(right_frame)
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

    def _block_separator_resize(event: tk.Event) -> str | None:
        if isinstance(event.widget, ttk.Treeview):
            region = event.widget.identify_region(event.x, event.y)
            if region == "separator":
                return "break"
        return None

    def _bind_fixed_width_columns(tree: ttk.Treeview) -> None:
        tree.bind("<Button-1>", _block_separator_resize, add="+")

    def _fit_structure_columns(_event: tk.Event | None = None) -> None:
        total_width = max(structure_tree.winfo_width(), 0)
        if total_width <= 1:
            return
        name_width = 240
        pct_width = 70
        slack = 6
        group_width = max(160, total_width - name_width - pct_width - slack)
        structure_tree.column("#0", width=name_width, minwidth=name_width, stretch=False)
        structure_tree.column("pct", width=pct_width, minwidth=pct_width, stretch=False)
        structure_tree.column("group", width=group_width, minwidth=160, anchor="w", stretch=False)

    def _fit_results_columns(_event: tk.Event | None = None) -> None:
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

    def _accelerated_units(delta: int, *, multiplier: int = 10) -> int:
        if delta == 0:
            return 0
        base_units = max(1, abs(int(delta)) // 120)
        return base_units * multiplier

    def _scroll_results_horizontally(direction: int, units: int) -> str:
        results_tree.xview_scroll(direction * units, "units")
        return "break"

    def _on_results_shift_mousewheel(event: tk.Event) -> str:
        delta = int(getattr(event, "delta", 0))
        units = _accelerated_units(delta)
        if units <= 0:
            return "break"
        direction = -1 if delta > 0 else 1
        return _scroll_results_horizontally(direction, units)

    def _on_results_shift_button4(_event: tk.Event) -> str:
        return _scroll_results_horizontally(-1, 3)

    def _on_results_shift_button5(_event: tk.Event) -> str:
        return _scroll_results_horizontally(1, 3)

    for widget in (results_tree, results_scroll_x):
        widget.bind("<Shift-MouseWheel>", _on_results_shift_mousewheel, add="+")
        widget.bind("<Shift-Button-4>", _on_results_shift_button4, add="+")
        widget.bind("<Shift-Button-5>", _on_results_shift_button5, add="+")

    _bind_fixed_width_columns(structure_tree)
    # _bind_fixed_width_columns(results_tree)
    structure_tree.bind("<Configure>", _fit_structure_columns, add="+")
    results_tree.bind("<Configure>", _fit_results_columns, add="+")

    def _build_live_column_meta(items: list[DistributionItem]) -> tuple[list[str], dict[str, str]]:
        column_ids = ["month", "fixed", "net_income"]
        headings = {
            "month": tr("common.month", "Месяц"),
            "fixed": tr("distribution.fixed", "Фиксация"),
            "net_income": (
                f"{tr('distribution.net_income', 'Чистый доход')} "
                f"({context.controller.get_display_currency_code()})"
            ),
        }
        for item in items:
            item_key = f"item_{item.id}"
            column_ids.append(item_key)
            headings[item_key] = item.name
            for subitem in context.controller.get_distribution_subitems(item.id):
                sub_key = f"sub_{subitem.id}"
                column_ids.append(sub_key)
                headings[sub_key] = f"  {subitem.name}"
        return column_ids, headings

    def _compose_column_meta(
        items: list[DistributionItem],
        visible_fixed_rows: list[FrozenDistributionRow],
    ) -> tuple[list[str], dict[str, str]]:
        column_ids, headings = _build_live_column_meta(items)
        for frozen_row in visible_fixed_rows:
            for column_id in frozen_row.column_order:
                if column_id not in headings:
                    column_ids.append(column_id)
                    headings[column_id] = frozen_row.headings_by_column.get(column_id, column_id)
        return column_ids, headings

    def _selected_item_id() -> int | None:
        selection = structure_tree.selection()
        if not selection:
            return None
        iid = selection[0]
        if iid.startswith("item_"):
            return int(iid.split("_", 1)[1])
        if iid.startswith("sub_"):
            parent_iid = structure_tree.parent(iid)
            if parent_iid.startswith("item_"):
                return int(parent_iid.split("_", 1)[1])
        return None

    def _refresh_validation() -> None:
        errors = context.controller.validate_distribution()
        if not errors:
            validation_label.config(
                text=tr(
                    "distribution.validation.ok",
                    "Структура корректна: верхний уровень и подэлементы суммарно дают 100.00%",
                ),
                foreground=palette.success,
            )
            return
        validation_label.config(
            text="\n".join(f"- {error.message}" for error in errors),
            foreground=palette.danger,
        )

    def _refresh_structure() -> None:
        structure_tree.delete(*structure_tree.get_children())
        try:
            items = context.controller.get_distribution_items()
        except (ValueError, TypeError, RuntimeError, tk.TclError) as exc:
            logger.warning("Failed to refresh distribution structure: %s", exc)
            validation_label.config(text=str(exc), foreground=palette.danger)
            return

        grouped: dict[str, list[DistributionItem]] = defaultdict(list)
        for item in items:
            grouped[item.group_name or tr("common.ungrouped", "Без группы")].append(item)

        for group_name in sorted(grouped, key=str.casefold):
            group_items = grouped[group_name]
            parent_iid = ""
            if len(group_items) > 1 or group_name != tr("common.ungrouped", "Без группы"):
                parent_iid = structure_tree.insert(
                    "",
                    "end",
                    text=group_name,
                    values=("", ""),
                    tags=("group_header",),
                    open=True,
                )
            for item in group_items:
                item_node = structure_tree.insert(
                    parent_iid,
                    "end",
                    iid=f"item_{item.id}",
                    text=item.name,
                    values=(f"{item.pct:.2f}%", item.group_name or ""),
                    tags=("item",),
                    open=True,
                )
                for subitem in context.controller.get_distribution_subitems(item.id):
                    structure_tree.insert(
                        item_node,
                        "end",
                        iid=f"sub_{subitem.id}",
                        text=subitem.name,
                        values=(f"{subitem.pct:.2f}%", ""),
                        tags=("subitem",),
                    )

        _fit_structure_columns()
        _refresh_validation()

    def _configure_results_columns(column_ids: list[str], headings: dict[str, str]) -> None:
        results_tree.configure(columns=column_ids, displaycolumns=column_ids)
        for column_id in column_ids:
            is_month = column_id == "month"
            is_sub = column_id.startswith("sub_")
            is_fixed = column_id == "fixed"
            width = 92 if is_sub else (60 if is_month else (50 if is_fixed else 90))
            anchor = "center" if is_fixed else ("w" if is_month else "e")
            results_tree.heading(column_id, text=headings[column_id])
            results_tree.column(column_id, width=width, anchor=anchor, stretch=False)
        _fit_results_columns()

    def _distribution_row_values_map(
        distribution: MonthlyDistribution,
        items: list[DistributionItem],
    ) -> dict[str, str]:
        item_results = {result.item.id: result for result in distribution.item_results}
        values = {
            "month": distribution.month,
            "fixed": "",
            "net_income": format_display_amount(distribution.net_income_base),
        }
        for item in items:
            result = item_results.get(item.id)
            item_key = f"item_{item.id}"
            if result is None:
                values[item_key] = "-"
                continue
            values[item_key] = format_display_amount(result.amount_base)
            sub_results = {sub.subitem.id: sub for sub in result.subitem_results}
            for subitem in context.controller.get_distribution_subitems(item.id):
                sub_key = f"sub_{subitem.id}"
                sub_result = sub_results.get(subitem.id)
                values[sub_key] = (
                    "-" if sub_result is None else format_display_amount(sub_result.amount_base)
                )
        return values

    def _row_values_for_columns(
        column_ids: list[str], values_by_column: dict[str, str]
    ) -> list[str]:
        return [values_by_column.get(column_id, "-") for column_id in column_ids]

    def _refresh_results() -> None:
        start_month = (period_from_var.get() or "").strip() or _default_start()
        end_month = (period_to_var.get() or "").strip() or _default_end()

        try:
            items = context.controller.get_distribution_items()
            history = context.controller.get_distribution_history(start_month, end_month)
            visible_fixed_rows = context.controller.get_frozen_distribution_rows(
                start_month,
                end_month,
            )
        except (ValueError, TypeError, RuntimeError, tk.TclError) as exc:
            logger.warning("Failed to refresh distribution results: %s", exc)
            status_label.config(text=str(exc), foreground=palette.danger)
            results_tree.delete(*results_tree.get_children())
            return

        live_history_by_month = {distribution.month: distribution for distribution in history}
        visible_fixed_rows_by_month = {row.month: row for row in visible_fixed_rows}
        visible_months = sorted(set(live_history_by_month) | set(visible_fixed_rows_by_month))

        if not items and not visible_fixed_rows:
            results_tree.delete(*results_tree.get_children())
            results_tree.configure(
                columns=("month", "fixed", "net_income"),
                displaycolumns=("month", "fixed", "net_income"),
            )
            results_tree.heading("month", text=tr("common.month", "Месяц"))
            results_tree.heading("fixed", text=tr("distribution.fixed", "Фиксация"))
            results_tree.heading("net_income", text=tr("distribution.net_income", "Чистый доход"))
            results_tree.column("month", width=80, minwidth=80, anchor="w", stretch=False)
            results_tree.column("fixed", width=80, minwidth=80, anchor="center", stretch=False)
            results_tree.column("net_income", width=130, minwidth=130, anchor="e", stretch=False)
            _fit_results_columns()
            status_label.config(
                text=tr(
                    "distribution.empty",
                    "Элементов распределения пока нет. "
                    "Добавьте структуру слева, чтобы заполнить таблицу.",
                ),
                foreground="",
            )
            fix_button.configure(
                state=tk.DISABLED, text=tr("distribution.fix", "Зафиксировать строку")
            )
            return

        column_ids, headings = _compose_column_meta(items, visible_fixed_rows)
        _configure_results_columns(column_ids, headings)
        results_tree.delete(*results_tree.get_children())
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
                values_by_column = _distribution_row_values_map(live_distribution, items)
            else:
                continue

            values_by_column["month"] = month
            values_by_column["fixed"] = "✓" if frozen_row is not None else ""
            tag = "neg_row" if is_negative else ("odd_row" if index % 2 == 0 else "even_row")
            results_tree.insert(
                "",
                "end",
                iid=month,
                values=_row_values_for_columns(column_ids, values_by_column),
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
        status_label.config(text=f"{status_text} ⓘ", foreground="")
        _update_fix_button_state()

    def _selected_result_month() -> str | None:
        selection = results_tree.selection()
        if not selection:
            return None
        return selection[0]

    def _update_fix_button_state(_event: tk.Event | None = None) -> None:
        month = _selected_result_month()
        if month is None:
            fix_button.configure(
                text=tr("distribution.fix", "Зафиксировать строку"), state=tk.DISABLED
            )
            return
        if context.controller.is_distribution_month_auto_fixed(month):
            fix_button.configure(text=tr("distribution.auto_fixed", "Автофикс"), state=tk.DISABLED)
            return
        button_text = (
            tr("distribution.unfix", "Снять фиксацию")
            if context.controller.is_distribution_month_fixed(month)
            else tr("distribution.fix", "Зафиксировать строку")
        )
        fix_button.configure(text=button_text, state=tk.NORMAL)

    def _toggle_fixed_row() -> None:
        month = _selected_result_month()
        if month is None:
            messagebox.showerror(
                tr("common.error", "Ошибка"),
                tr("distribution.error.select_month", "Сначала выберите месяц в таблице."),
            )
            return
        try:
            context.controller.toggle_distribution_month_fixed(month)
        except ValueError as exc:
            messagebox.showinfo(tr("tab.distribution", "Распределение"), str(exc), parent=parent)
            _update_fix_button_state()
            return
        _refresh_results()
        if results_tree.exists(month):
            results_tree.selection_set(month)
            results_tree.focus(month)
        _update_fix_button_state()

    def _refresh_all() -> None:
        _refresh_structure()
        _refresh_results()

    def _ask_pct(title: str, prompt: str, *, initialvalue: str = "0.00") -> float | None:
        def _validate(value: str) -> str | None:
            return None

        raw_value = ask_numeric_text(
            title,
            prompt,
            parent=parent,
            initialvalue=initialvalue,
            validator=_validate,
        )
        if raw_value is None:
            return None
        return float(raw_value)

    def _add_item() -> None:
        name = ask_text(
            tr("distribution.dialog.new_item", "Новый элемент"),
            tr("distribution.dialog.item_name", "Название элемента:"),
            parent=parent,
        )
        if not name:
            return
        group_name = ask_text(
            tr("common.group", "Группа"),
            tr("distribution.dialog.group_name", "Необязательное имя группы:"),
            parent=parent,
        )
        pct = _ask_pct(
            tr("distribution.dialog.percent", "Процент"),
            tr(
                "distribution.dialog.percent_total", "Процент от общего месячного денежного потока:"
            ),
        )
        if pct is None:
            return
        try:
            context.controller.create_distribution_item(
                name,
                group_name=group_name or "",
                pct=pct,
            )
        except ValueError as exc:
            messagebox.showerror(tr("tab.distribution", "Распределение"), str(exc))
            return
        _refresh_all()

    def _add_subitem() -> None:
        item_id = _selected_item_id()
        if item_id is None:
            messagebox.showerror(
                tr("common.error", "Ошибка"),
                tr(
                    "distribution.error.select_top_level",
                    "Сначала выберите элемент верхнего уровня.",
                ),
            )
            return
        name = ask_text(
            tr("distribution.dialog.new_subitem", "Новый подэлемент"),
            tr("distribution.dialog.subitem_name", "Название подэлемента:"),
            parent=parent,
        )
        if not name:
            return
        pct = _ask_pct(
            tr("distribution.dialog.percent", "Процент"),
            tr("distribution.dialog.percent_parent", "Процент от родительского элемента:"),
        )
        if pct is None:
            return
        try:
            context.controller.create_distribution_subitem(item_id, name, pct=pct)
        except ValueError as exc:
            messagebox.showerror(tr("tab.distribution", "Распределение"), str(exc))
            return
        _refresh_all()

    def _edit_pct() -> None:
        selection = structure_tree.selection()
        if not selection:
            messagebox.showerror(
                tr("common.error", "Ошибка"),
                tr("distribution.error.select_item", "Сначала выберите элемент или подэлемент."),
            )
            return
        iid = selection[0]
        if not (iid.startswith("item_") or iid.startswith("sub_")):
            messagebox.showerror(
                tr("common.error", "Ошибка"),
                tr(
                    "distribution.error.select_not_group",
                    "Выберите элемент или подэлемент, а не заголовок группы.",
                ),
            )
            return
        current_value = str(structure_tree.item(iid, "values")[0]).rstrip("%").strip() or "0.00"
        pct = _ask_pct(
            tr("distribution.dialog.edit_percent", "Изменить процент"),
            tr("distribution.dialog.new_percent", "Новый процент:"),
            initialvalue=current_value,
        )
        if pct is None:
            return
        try:
            if iid.startswith("item_"):
                context.controller.update_distribution_item_pct(int(iid.split("_", 1)[1]), pct)
            else:
                context.controller.update_distribution_subitem_pct(int(iid.split("_", 1)[1]), pct)
        except ValueError as exc:
            messagebox.showerror(
                tr("distribution.error.title", "Ошибка распределения"),
                str(exc),
            )
            return
        _refresh_all()

    def _rename() -> None:
        selection = structure_tree.selection()
        if not selection:
            messagebox.showerror(
                tr("distribution.error.selection_title", "Требуется выбор"),
                tr(
                    "distribution.error.selection_item_or_subitem",
                    "Сначала выберите элемент или подэлемент.",
                ),
            )
            return
        iid = selection[0]
        if not (iid.startswith("item_") or iid.startswith("sub_")):
            messagebox.showerror(
                tr("distribution.error.selection_title", "Требуется выбор"),
                tr(
                    "distribution.error.selection_not_group_header",
                    "Выберите элемент или подэлемент, а не заголовок группы.",
                ),
            )
            return
        current_name = structure_tree.item(iid, "text").strip()
        new_name = ask_text(
            tr("distribution.dialog.rename", "Переименование"),
            tr("distribution.dialog.new_name", "Новое имя:"),
            parent=parent,
            initialvalue=current_name,
        )
        if not new_name:
            return
        try:
            if iid.startswith("item_"):
                context.controller.update_distribution_item_name(
                    int(iid.split("_", 1)[1]), new_name
                )
            else:
                context.controller.update_distribution_subitem_name(
                    int(iid.split("_", 1)[1]),
                    new_name,
                )
        except ValueError as exc:
            messagebox.showerror(
                tr("distribution.error.title", "Ошибка распределения"),
                str(exc),
            )
            return
        _refresh_all()

    def _delete_selected() -> None:
        selection = structure_tree.selection()
        if not selection:
            messagebox.showerror(
                tr("distribution.error.selection_title", "Требуется выбор"),
                tr(
                    "distribution.error.selection_delete_item",
                    "Выберите элемент или подэлемент для удаления.",
                ),
            )
            return
        iid = selection[0]
        if not (iid.startswith("item_") or iid.startswith("sub_")):
            messagebox.showerror(
                tr("distribution.error.selection_title", "Требуется выбор"),
                tr(
                    "distribution.error.delete_group_header_forbidden",
                    "Заголовки групп нельзя удалять напрямую.",
                ),
            )
            return
        name = structure_tree.item(iid, "text").strip()
        message = tr("distribution.confirm.delete_item", "Удалить '{name}'?", name=name)
        if iid.startswith("item_"):
            message += "\n" + tr(
                "distribution.confirm.delete_item_with_children",
                "Все дочерние подэлементы также будут удалены.",
            )
        if not messagebox.askyesno(
            tr("distribution.confirm.delete_title", "Подтвердите удаление"),
            message,
            parent=parent,
        ):
            return
        try:
            if iid.startswith("item_"):
                context.controller.delete_distribution_item(int(iid.split("_", 1)[1]))
            else:
                context.controller.delete_distribution_subitem(int(iid.split("_", 1)[1]))
        except ValueError as exc:
            messagebox.showerror(
                tr("distribution.error.title", "Ошибка распределения"),
                str(exc),
            )
            return
        _refresh_all()

    ttk.Button(
        buttons,
        text=tr("distribution.button.add_item", "+ Элемент"),
        command=_add_item,
    ).pack(side=tk.LEFT, padx=(0, 4))
    ttk.Button(
        buttons,
        text=tr("distribution.button.add_subitem", "+ Подэлемент"),
        command=_add_subitem,
    ).pack(side=tk.LEFT, padx=4)
    ttk.Button(
        buttons,
        text=tr("distribution.button.edit_percent", "Изменить %"),
        command=_edit_pct,
    ).pack(side=tk.LEFT, padx=4)
    ttk.Button(
        buttons,
        text=tr("distribution.button.rename", "Переименовать"),
        command=_rename,
    ).pack(side=tk.LEFT, padx=4)
    ttk.Button(
        buttons,
        text=tr("distribution.button.delete", "Удалить"),
        command=_delete_selected,
    ).pack(side=tk.LEFT, padx=4)
    ttk.Button(
        toolbar,
        text=tr("distribution.button.refresh", "Обновить"),
        command=_refresh_all,
    ).pack(side=tk.LEFT, padx=(4, 0))
    fix_button.configure(command=_toggle_fixed_row, state=tk.DISABLED)
    results_tree.bind("<<TreeviewSelect>>", _update_fix_button_state, add="+")

    _refresh_all()
    return DistributionTabBindings(
        structure_tree=structure_tree,
        validation_label=validation_label,
        period_from_var=period_from_var,
        period_to_var=period_to_var,
        results_tree=results_tree,
        status_label=status_label,
        refresh=_refresh_all,
    )


def _fmt_amount(value: float) -> str:
    if abs(value) < 0.005:
        return "-"
    return f"{value:,.0f}"


def _default_start() -> str:
    today = dt_date.today()
    return f"{today.year:04d}-01"


def _default_end() -> str:
    today = dt_date.today()
    return f"{today.year:04d}-{today.month:02d}"
