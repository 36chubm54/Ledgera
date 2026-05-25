from __future__ import annotations

import logging
import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass
from tkinter import ttk
from typing import Any, Protocol

from domain.errors import DomainError
from gui.i18n import tr
from gui.logging_utils import log_ui_error
from gui.ui_helpers import parse_numeric_input

from .forms import (
    MandatoryAddFormFields,
    MandatoryAddToRecordsFields,
    MandatoryEditFormFields,
    mandatory_date_text,
)


class MessageBoxLike(Protocol):
    def showerror(self, title: str, message: str) -> Any: ...

    def showinfo(self, title: str, message: str) -> Any: ...

    def askyesno(self, title: str, message: str) -> bool: ...


@dataclass(slots=True)
class MandatorySectionActionContext:
    context: Any
    refresh_mandatory: Callable[[], None]
    refresh_wallets: Callable[[], None]
    close_inline_panels: Callable[[], None]
    base_currency_code: str
    messagebox_module: MessageBoxLike
    logger: logging.Logger


def selected_mandatory_index(
    mand_tree: ttk.Treeview,
    *,
    messagebox_module: MessageBoxLike,
    missing_message: str,
) -> int | None:
    selection = mand_tree.selection()
    if not selection:
        messagebox_module.showerror(tr("common.error", "Ошибка"), missing_message)
        return None
    try:
        return int(selection[0])
    except (TypeError, ValueError):
        messagebox_module.showerror(
            tr("common.error", "Ошибка"),
            tr("common.invalid_selection", "Некорректный выбор."),
        )
        return None


def clear_create_form(
    form: MandatoryAddFormFields,
    *,
    base_currency_code: str,
) -> None:
    form.amount_entry.delete(0, tk.END)
    form.currency_entry.delete(0, tk.END)
    form.currency_entry.insert(0, base_currency_code)
    form.category_entry.delete(0, tk.END)
    form.category_entry.insert(0, "Mandatory")
    form.description_entry.delete(0, tk.END)
    form.period_var.set("monthly")
    form.date_entry.delete(0, tk.END)


def save_create_form(
    form: MandatoryAddFormFields,
    runtime: MandatorySectionActionContext,
) -> None:
    wallet_id = None
    try:
        amount = parse_numeric_input(form.amount_entry.get())
        description = form.description_entry.get()
        if not description:
            runtime.messagebox_module.showerror(
                tr("common.error", "Ошибка"),
                tr("mandatory.error.description_required", "Описание обязательно."),
            )
            return
        date_val = form.date_entry.get().strip()
        if date_val:
            try:
                from domain.validation import parse_ymd

                parse_ymd(date_val)
            except ValueError:
                runtime.messagebox_module.showerror(
                    tr("common.error", "Ошибка"),
                    tr(
                        "mandatory.error.invalid_date",
                        "Некорректная дата. Используйте YYYY-MM-DD.",
                    ),
                )
                return
        wallet_id = form.wallet_map.get(form.wallet_var.get())
        if wallet_id is None:
            runtime.messagebox_module.showerror(
                tr("common.error", "Ошибка"),
                tr("mandatory.error.wallet_required", "Кошелек обязателен."),
            )
            return
        runtime.context.controller.create_mandatory_expense(
            amount=amount,
            currency=(form.currency_entry.get() or runtime.base_currency_code).strip(),
            wallet_id=wallet_id,
            category=(form.category_entry.get() or "Mandatory").strip(),
            description=description,
            period=form.period_var.get(),
            date=date_val,
        )
        runtime.messagebox_module.showinfo(
            tr("common.done", "Готово"),
            tr("mandatory.added", "Обязательный расход добавлен."),
        )
        clear_create_form(form, base_currency_code=runtime.base_currency_code)
        runtime.context._refresh_charts()
        runtime.refresh_mandatory()
        runtime.context._refresh_budgets()
    except (DomainError, ValueError, TypeError, RuntimeError) as error:
        log_ui_error(
            runtime.logger,
            "UI_SETTINGS_MANDATORY_CREATE_FAILED",
            error,
            wallet_id=wallet_id,
        )
        runtime.messagebox_module.showerror(
            tr("common.error", "Ошибка"),
            tr(
                "mandatory.error.add_failed",
                "Не удалось добавить расход: {error}",
                error=error,
            ),
        )


def save_edit_form(
    form: MandatoryEditFormFields,
    *,
    expense: Any,
    runtime: MandatorySectionActionContext,
) -> None:
    expense_id = int(expense.id)
    raw_amount = form.amount_base_entry.get().strip()
    current_amount = str(expense.amount_base)
    if raw_amount != current_amount:
        try:
            runtime.context.controller.update_mandatory_expense_amount_base(
                expense_id, parse_numeric_input(raw_amount)
            )
        except ValueError as error:
            runtime.messagebox_module.showerror(
                tr("mandatory.error.amount_title", "Ошибка суммы"), str(error)
            )
            return

    new_wallet_id = form.wallet_map.get(form.wallet_var.get())
    if new_wallet_id is None:
        runtime.messagebox_module.showerror(
            tr("common.error", "Ошибка"),
            tr("mandatory.error.wallet_required", "Кошелек обязателен."),
        )
        return
    if int(new_wallet_id) != int(expense.wallet_id):
        try:
            runtime.context.controller.update_mandatory_expense_wallet_id(
                expense_id, int(new_wallet_id)
            )
        except ValueError as error:
            runtime.messagebox_module.showerror(
                tr("mandatory.error.wallet_title", "Ошибка кошелька"), str(error)
            )
            return

    new_period = str(form.period_var.get() or "").strip().lower()
    if new_period and str(new_period) != str(expense.period):
        try:
            runtime.context.controller.update_mandatory_expense_period(expense_id, new_period)
        except ValueError as error:
            runtime.messagebox_module.showerror(
                tr("mandatory.error.period_title", "Ошибка периода"), str(error)
            )
            return

    current_date = mandatory_date_text(expense)
    new_date = form.date_entry.get().strip()
    if new_date != current_date:
        try:
            runtime.context.controller.update_mandatory_expense_date(expense_id, new_date)
        except ValueError as error:
            runtime.messagebox_module.showerror(
                tr("mandatory.error.date_title", "Ошибка даты"), str(error)
            )
            return

    runtime.close_inline_panels()
    runtime.refresh_mandatory()
    runtime.context._refresh_charts()
    runtime.context._refresh_budgets()
    runtime.messagebox_module.showinfo(
        tr("common.done", "Готово"),
        tr("mandatory.updated", "Обязательный расход обновлен."),
    )


def save_add_to_records(
    index: int,
    form: MandatoryAddToRecordsFields,
    runtime: MandatorySectionActionContext,
) -> None:
    try:
        from domain.validation import ensure_not_future, parse_ymd

        date_value = form.date_entry.get()
        entered_date = parse_ymd(date_value)
        ensure_not_future(entered_date)
        wallet_id = form.wallet_map.get(form.wallet_var.get())
        if wallet_id is None:
            runtime.messagebox_module.showerror(
                tr("common.error", "Ошибка"),
                tr("mandatory.error.wallet_required", "Кошелек обязателен."),
            )
            return

        runtime.context.controller.add_mandatory_to_report(index, date_value, wallet_id)
        runtime.messagebox_module.showinfo(
            tr("common.done", "Готово"),
            tr(
                "mandatory.added_to_records",
                "Обязательный расход добавлен в записи за {date}.",
                date=date_value,
            ),
        )
        runtime.close_inline_panels()
        runtime.refresh_mandatory()
        runtime.refresh_wallets()
        runtime.context._refresh_list()
        runtime.context._refresh_charts()
        runtime.context._refresh_budgets()
        runtime.context._refresh_all()
    except ValueError as error:
        runtime.messagebox_module.showerror(
            tr("common.error", "Ошибка"),
            tr(
                "mandatory.error.invalid_date_with_hint",
                "Некорректная дата: {error}. Используйте YYYY-MM-DD.",
                error=error,
            ),
        )


def delete_mandatory(
    index: int,
    runtime: MandatorySectionActionContext,
) -> None:
    if runtime.context.controller.delete_mandatory_expense(index):
        runtime.messagebox_module.showinfo(
            tr("common.done", "Готово"),
            tr("mandatory.deleted", "Обязательный расход удален."),
        )
        runtime.refresh_mandatory()
    else:
        runtime.messagebox_module.showerror(
            tr("common.error", "Ошибка"),
            tr(
                "mandatory.error.delete_failed",
                "Не удалось удалить обязательный расход.",
            ),
        )


def delete_all_mandatory(runtime: MandatorySectionActionContext) -> None:
    if not runtime.messagebox_module.askyesno(
        tr("common.confirm", "Подтверждение"),
        tr(
            "mandatory.confirm_delete_all",
            "Удалить ВСЕ обязательные расходы? Это действие нельзя отменить.",
        ),
    ):
        return
    runtime.context.controller.delete_all_mandatory_expenses()
    runtime.messagebox_module.showinfo(
        tr("common.done", "Готово"),
        tr("mandatory.deleted_all", "Все обязательные расходы удалены."),
    )
    runtime.refresh_mandatory()
