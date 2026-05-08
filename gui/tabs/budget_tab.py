"""Budget tab - budget planning and spend tracking."""

from __future__ import annotations

import logging
import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass
from tkinter import ttk
from typing import Any, Protocol

from domain.budget import Budget, BudgetResult, BudgetStatus, PaceStatus
from gui.i18n import tr
from gui.tooltip import Tooltip
from gui.ui_helpers import (
    ask_confirm,
    ask_text,
    attach_treeview_scrollbars,
    bind_label_wrap,
    set_status,
    show_error,
)
from gui.ui_theme import (
    PAD_LG,
    PAD_SM,
    PAD_XL,
    PAD_XS,
    create_card_section,
    enable_treeview_zebra,
    get_palette,
)

logger = logging.getLogger(__name__)


class BudgetTabContext(Protocol):
    controller: Any

    def _refresh_charts(self) -> None: ...


@dataclass(slots=True)
class BudgetTabBindings:
    category_combo: ttk.Combobox
    start_date_entry: ttk.Entry
    end_date_entry: ttk.Entry
    limit_entry: ttk.Entry
    include_mandatory_var: tk.BooleanVar
    budget_tree: ttk.Treeview
    progress_canvas: tk.Canvas
    status_label: ttk.Label
    refresh: Callable[[], None]
    add_budget: Callable[[], None]
    edit_budget: Callable[[], None]
    delete_budget: Callable[[], None]


def _visual_budget_state(result: BudgetResult) -> str:
    if result.status == BudgetStatus.FUTURE:
        return "future"
    if result.status == BudgetStatus.EXPIRED:
        return "expired"
    return result.pace_status.value


def _draw_progress_bars(canvas: tk.Canvas, results: list[BudgetResult]) -> None:
    palette = get_palette()
    pace_fill = {
        PaceStatus.ON_TRACK: palette.success,
        PaceStatus.OVERPACE: palette.warning,
        PaceStatus.OVERSPENT: palette.danger,
    }
    canvas.delete("all")
    canvas.configure(bg=palette.surface_elevated, highlightbackground=palette.border_soft)
    if not results:
        return

    width = max(canvas.winfo_width(), 400)
    bar_h = 12
    gap = 7
    pad_l = 115
    pad_r = 48
    bar_w = max(40, width - pad_l - pad_r)

    total_h = len(results) * (bar_h + gap) + gap
    canvas.configure(height=max(40, total_h))

    for index, result in enumerate(results):
        y = gap + index * (bar_h + gap)
        canvas.create_text(
            pad_l - 6,
            y + bar_h // 2,
            text=result.budget.category[:15],
            anchor="e",
            fill=palette.chart_text,
            font=("Segoe UI", 9),
        )
        canvas.create_rectangle(
            pad_l,
            y,
            pad_l + bar_w,
            y + bar_h,
            fill=palette.surface_alt,
            outline="",
        )

        fill_w = min(bar_w, max(0, int(bar_w * result.usage_pct / 100.0)))
        if fill_w > 0:
            visual_state = _visual_budget_state(result)
            if visual_state in {"future", "expired"}:
                fill_color = palette.text_muted
            else:
                fill_color = pace_fill.get(result.pace_status, palette.success)
            canvas.create_rectangle(
                pad_l,
                y,
                pad_l + fill_w,
                y + bar_h,
                fill=fill_color,
                outline="",
            )

        if result.status == BudgetStatus.ACTIVE:
            tx = pad_l + max(0, min(bar_w, int(bar_w * result.time_pct / 100.0)))
            canvas.create_line(tx, y - 1, tx, y + bar_h + 1, fill=palette.accent_blue, width=2)

        canvas.create_text(
            pad_l + bar_w + 6,
            y + bar_h // 2,
            text=f"{result.usage_pct:.0f}%",
            anchor="w",
            fill=palette.chart_text,
            font=("Segoe UI", 9),
        )


def build_budget_tab(
    parent: tk.Frame | ttk.Frame,
    *,
    context: BudgetTabContext,
) -> BudgetTabBindings:
    palette = get_palette()
    parent.grid_columnconfigure(0, weight=1)
    parent.grid_rowconfigure(1, weight=1)

    form_card = create_card_section(parent, tr("budget.new", "Новый бюджет"))
    form_card.grid(row=0, column=0, sticky="ew", padx=PAD_XL, pady=(PAD_LG, PAD_SM))
    form_frame = form_card.winfo_children()[-1]
    for col in (1, 3, 5):
        form_frame.grid_columnconfigure(col, weight=1)

    ttk.Label(form_frame, text=tr("common.category", "Категория:")).grid(
        row=0, column=0, sticky="w", padx=PAD_SM, pady=PAD_XS
    )
    category_combo = ttk.Combobox(form_frame, state="normal", width=20)
    category_combo.grid(row=0, column=1, sticky="ew", padx=PAD_SM, pady=PAD_XS)

    scope_type_var = tk.StringVar(value="category")
    ttk.Label(form_frame, text=tr("budget.scope", "Тип:")).grid(
        row=1, column=0, sticky="w", padx=PAD_SM, pady=PAD_XS
    )
    scope_type_combo = ttk.Combobox(
        form_frame,
        state="readonly",
        textvariable=scope_type_var,
        values=("category", "tag"),
        width=16,
    )
    scope_type_combo.grid(row=1, column=1, sticky="ew", padx=PAD_SM, pady=PAD_XS)

    ttk.Label(form_frame, text=tr("common.from", "С даты:")).grid(
        row=0, column=2, sticky="w", padx=PAD_SM, pady=PAD_XS
    )
    start_date_entry = ttk.Entry(form_frame, width=12)
    start_date_entry.grid(row=0, column=3, sticky="ew", padx=PAD_SM, pady=PAD_XS)

    ttk.Label(form_frame, text=tr("common.to", "По дату:")).grid(
        row=0, column=4, sticky="w", padx=PAD_SM, pady=PAD_XS
    )
    end_date_entry = ttk.Entry(form_frame, width=12)
    end_date_entry.grid(row=0, column=5, sticky="ew", padx=PAD_SM, pady=PAD_XS)

    ttk.Label(form_frame, text=tr("budget.limit_kzt", "Лимит (KZT):")).grid(
        row=2, column=0, sticky="w", padx=PAD_SM, pady=PAD_XS
    )
    limit_entry = ttk.Entry(form_frame, width=16)
    limit_entry.grid(row=2, column=1, sticky="ew", padx=PAD_SM, pady=PAD_XS)

    include_mandatory_var = tk.BooleanVar(value=False)
    include_mandatory_check = ttk.Checkbutton(
        form_frame,
        text=tr("budget.include_mandatory", "Учитывать обязательные расходы"),
        variable=include_mandatory_var,
    )
    include_mandatory_check.grid(
        row=2, column=2, columnspan=2, sticky="w", padx=PAD_SM, pady=PAD_XS
    )
    Tooltip(
        include_mandatory_check,
        tr(
            "budget.include_mandatory.tooltip",
            "Учитываются только обязательные расходы, уже добавленные в операции,"
            "\nесли категория совпадает, а дата попадает в период бюджета.",
        ),
    )

    list_frame = ttk.Frame(parent)
    list_frame.grid(row=1, column=0, sticky="nsew", padx=PAD_XL, pady=(0, PAD_SM))
    list_frame.grid_columnconfigure(0, weight=1)
    list_frame.grid_rowconfigure(0, weight=1)

    columns = (
        "category",
        "period",
        "include",
        "limit",
        "spent",
        "remaining",
        "usage",
        "pace",
        "status",
    )
    budget_tree = ttk.Treeview(list_frame, columns=columns, show="headings", height=10)
    enable_treeview_zebra(budget_tree)

    for col, text, width, anchor in (
        ("category", tr("common.category_short", "Категория"), 170, "w"),
        ("period", tr("common.period", "Период"), 180, "w"),
        ("include", tr("budget.include_short", "Обязательные"), 120, "center"),
        ("limit", tr("budget.limit", "Лимит"), 70, "e"),
        ("spent", tr("budget.spent", "Потрачено"), 100, "e"),
        ("remaining", tr("budget.remaining", "Остаток"), 100, "e"),
        ("usage", tr("budget.usage_short", "%"), 65, "center"),
        ("pace", tr("budget.pace", "Темп"), 85, "center"),
        ("status", tr("common.status", "Статус"), 250, "center"),
    ):
        budget_tree.heading(col, text=text)
        budget_tree.column(col, width=width, anchor=anchor)  # type: ignore[arg-type]

    budget_tree.tag_configure("overspent", foreground=palette.danger)
    budget_tree.tag_configure("overpace", foreground=palette.warning)
    budget_tree.tag_configure("on_track", foreground=palette.success)
    budget_tree.tag_configure("future", foreground=palette.text_muted)
    budget_tree.tag_configure("expired", foreground=palette.text_muted)

    budget_tree.grid(row=0, column=0, sticky="nsew")
    attach_treeview_scrollbars(list_frame, budget_tree, row=0, column=0, horizontal=True)

    progress_canvas = tk.Canvas(
        list_frame,
        height=40,
        bg=palette.surface_elevated,
        highlightthickness=0,
        highlightbackground=palette.border_soft,
    )
    progress_canvas.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(2, 0))
    last_results: list[BudgetResult] = []

    def _redraw_progress_on_resize(_event: tk.Event | None = None) -> None:
        _draw_progress_bars(progress_canvas, last_results)

    progress_canvas.bind("<Configure>", _redraw_progress_on_resize)

    legend_label = ttk.Label(
        list_frame,
        text=tr(
            "budget.legend",
            "Зеленый: норма, янтарный: выше темпа, красный: перерасход, синяя линия: прошедшая часть периода."  # noqa: E501
            "\nСтатус 'Выше темпа' включается, когда расход опережает линию времени более чем на 10 п.п.",  # noqa: E501
        ),
        style="Subtle.TLabel",
    )
    legend_label.grid(row=3, column=0, columnspan=2, sticky="ew", padx=4)
    bind_label_wrap(legend_label, list_frame, max_width=840)

    btn_frame = ttk.Frame(list_frame)
    btn_frame.grid(row=4, column=0, columnspan=2, sticky="w", pady=4)
    status_label = ttk.Label(list_frame, text="")
    status_label.grid(row=5, column=0, columnspan=2, sticky="w", padx=4)

    def _clear_form() -> None:
        category_combo.set("")
        scope_type_var.set("category")
        start_date_entry.delete(0, tk.END)
        end_date_entry.delete(0, tk.END)
        limit_entry.delete(0, tk.END)
        include_mandatory_var.set(False)

    def _row_tag(result: BudgetResult) -> str:
        return _visual_budget_state(result)

    def _display_pace_status(pace_status: PaceStatus) -> str:
        return {
            PaceStatus.ON_TRACK: tr("budget.pace_status.on_track", "В норме"),
            PaceStatus.OVERPACE: tr("budget.pace_status.overpace", "Выше темпа"),
            PaceStatus.OVERSPENT: tr("budget.pace_status.overspent", "Перерасход"),
        }.get(pace_status, str(pace_status.value))

    def _display_budget_status(status: BudgetStatus) -> str:
        return {
            BudgetStatus.FUTURE: tr("budget.status_value.future", "Будущий"),
            BudgetStatus.ACTIVE: tr("budget.status_value.active", "Активный"),
            BudgetStatus.EXPIRED: tr("budget.status_value.expired", "Завершен"),
        }.get(status, str(status.value))

    def _display_forecast_status(result: BudgetResult) -> str | None:
        if not result.forecast_status_key:
            return None
        params = dict(result.forecast_status_params or {})
        fallbacks = {
            "budget.forecast.overspend_in_days": "Прогноз перерасхода через {days} дн.",
            "budget.forecast.overspend": "Прогноз перерасхода",
            "budget.forecast.remaining": "Прогноз остатка: {amount_kzt:,.0f} KZT",
        }
        return tr(
            result.forecast_status_key,
            fallbacks.get(result.forecast_status_key, ""),
            **params,
        )

    def _refresh() -> None:
        nonlocal last_results
        try:
            if scope_type_var.get() == "tag":
                category_combo["values"] = [tag.name for tag in context.controller.list_tags()]
            else:
                categories = set(context.controller.get_expense_categories())
                categories.update(context.controller.get_mandatory_expense_categories())
                category_combo["values"] = sorted(categories, key=lambda value: value.casefold())
        except (ValueError, TypeError, RuntimeError, tk.TclError):
            logger.debug("Failed to refresh budget category suggestions", exc_info=True)

        try:
            results = context.controller.get_budget_results()
        except (ValueError, TypeError, RuntimeError) as err:
            logger.warning("Budget refresh error: %s", err)
            return

        last_results = list(results)
        budget_tree.delete(*budget_tree.get_children())
        for result in results:
            budget = result.budget
            forecast_status = _display_forecast_status(result)
            budget_tree.insert(
                "",
                "end",
                iid=str(budget.id),
                values=(
                    budget.category,
                    f"{budget.start_date}  ->  {budget.end_date}",
                    tr("common.yes", "Да") if budget.include_mandatory else tr("common.no", "Нет"),
                    f"{budget.limit_kzt:,.0f}",
                    f"{result.spent_kzt:,.0f}",
                    f"{result.remaining_kzt:,.0f}",
                    f"{result.usage_pct:.1f}%",
                    _display_pace_status(result.pace_status),
                    forecast_status if forecast_status else _display_budget_status(result.status),
                ),
                tags=(_row_tag(result),),
            )

        progress_canvas.after(50, lambda: _draw_progress_bars(progress_canvas, last_results))
        active_count = sum(1 for item in results if item.status == BudgetStatus.ACTIVE)
        set_status(
            status_label,
            tr(
                "budget.status.active",
                "Активных бюджетов: {active} из {total}",
                active=active_count,
                total=len(results),
            ),
            tone="success" if active_count else "muted",
        )

    def _find_selected_budget() -> Budget | None:
        selection = budget_tree.selection()
        if not selection:
            return None
        try:
            budget_id = int(selection[0])
        except (TypeError, ValueError):
            return None
        budgets = context.controller.get_budgets()
        return next((budget for budget in budgets if int(budget.id) == budget_id), None)

    def _add_budget() -> None:
        category = category_combo.get().strip()
        scope_type = scope_type_var.get().strip() or "category"
        start_date = start_date_entry.get().strip()
        end_date = end_date_entry.get().strip()
        raw_limit = limit_entry.get().strip()

        if not category:
            show_error(tr("budget.error.category_required", "Укажите категорию."))
            return
        if not start_date or not end_date:
            show_error(
                tr(
                    "budget.error.date_required",
                    "Укажите начальную и конечную дату в формате ГГГГ-ММ-ДД.",
                )
            )
            return
        try:
            limit_kzt = float(raw_limit.replace(" ", "").replace(",", "."))
            if limit_kzt <= 0:
                raise ValueError
        except ValueError:
            show_error(tr("budget.error.limit_positive", "Лимит должен быть положительным числом."))
            return

        try:
            context.controller.create_budget(
                category=category,
                start_date=start_date,
                end_date=end_date,
                limit_kzt=limit_kzt,
                include_mandatory=include_mandatory_var.get(),
                scope_type=scope_type,
                scope_value=category,
            )
        except ValueError as error:
            show_error(str(error), title=tr("budget.error.title", "Ошибка бюджета"))
            return

        _clear_form()
        _refresh()

    def _delete_budget() -> None:
        target = _find_selected_budget()
        if target is None:
            show_error(tr("budget.error.select_first", "Сначала выберите бюджет."))
            return
        if not ask_confirm(
            tr(
                "budget.delete.confirm",
                "Удалить бюджет '{category}'\n{start_date} -> {end_date}?",
                category=target.category,
                start_date=target.start_date,
                end_date=target.end_date,
            ),
            title=tr("operations.delete_all.title", "Подтвердите удаление"),
        ):
            return
        try:
            context.controller.delete_budget(target.id)
        except ValueError as error:
            show_error(str(error))
            return
        _refresh()

    def _edit_limit() -> None:
        target = _find_selected_budget()
        if target is None:
            show_error(tr("budget.error.select_first", "Сначала выберите бюджет."))
            return
        new_limit_str = ask_text(
            tr("budget.limit.title", "Изменение лимита"),
            tr(
                "budget.limit.prompt",
                "Новый лимит (KZT) для '{category}':",
                category=target.category,
            ),
            initialvalue=f"{target.limit_kzt:,.0f}",
            parent=parent,
        )
        if not new_limit_str:
            return
        normalized = new_limit_str.replace(" ", "")
        if "," in normalized and "." not in normalized:
            normalized = normalized.replace(",", ".")
        else:
            normalized = normalized.replace(",", "")
        try:
            context.controller.update_budget_limit(target.id, float(normalized))
        except (ValueError, TypeError) as error:
            show_error(tr("budget.error.invalid_limit", "Некорректный лимит: {error}", error=error))
            return
        _refresh()

    ttk.Button(
        form_frame,
        text=tr("budget.create", "Создать бюджет"),
        style="Primary.TButton",
        command=_add_budget,
    ).grid(row=2, column=4, padx=6, pady=4)
    ttk.Button(form_frame, text=tr("budget.clear", "Очистить"), command=_clear_form).grid(
        row=2, column=5, padx=6, pady=4
    )

    scope_type_combo.bind("<<ComboboxSelected>>", lambda _event: _refresh())
    ttk.Button(
        btn_frame,
        text=tr("budget.edit_limit", "Изменить лимит"),
        command=_edit_limit,
    ).pack(side=tk.LEFT, padx=4)
    ttk.Button(btn_frame, text=tr("common.delete", "Удалить"), command=_delete_budget).pack(
        side=tk.LEFT, padx=4
    )
    ttk.Button(btn_frame, text=tr("common.refresh", "Обновить"), command=_refresh).pack(
        side=tk.LEFT, padx=4
    )

    _refresh()
    return BudgetTabBindings(
        category_combo=category_combo,
        start_date_entry=start_date_entry,
        end_date_entry=end_date_entry,
        limit_entry=limit_entry,
        include_mandatory_var=include_mandatory_var,
        budget_tree=budget_tree,
        progress_canvas=progress_canvas,
        status_label=status_label,
        refresh=_refresh,
        add_budget=_add_budget,
        edit_budget=_edit_limit,
        delete_budget=_delete_budget,
    )
