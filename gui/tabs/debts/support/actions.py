from __future__ import annotations

# ruff: noqa: E501
import logging
import tkinter as tk
from collections.abc import Callable
from tkinter import ttk

from domain.debt import Debt, DebtKind
from domain.errors import DomainError
from gui.i18n import tr
from gui.logging_utils import log_ui_error
from gui.ui_helpers import parse_numeric_input

from ..core.contracts import refresh_debts_views
from .history_section import selected_debt

logger = logging.getLogger(__name__)


def refresh_wallets(
    context,
    *,
    wallet_menu: ttk.Combobox,
    action_wallet_menu: ttk.Combobox,
    wallet_var: tk.StringVar,
    action_wallet_var: tk.StringVar,
) -> dict[str, int]:
    wallets = context.controller.load_active_wallets()
    wallet_map = {
        f"[{wallet.id}] {wallet.name} ({wallet.currency})": wallet.id for wallet in wallets
    }
    labels = list(wallet_map.keys()) or [""]
    for combo_widget, var in (
        (wallet_menu, wallet_var),
        (action_wallet_menu, action_wallet_var),
    ):
        combo_widget["values"] = labels
        if var.get() not in wallet_map:
            var.set(labels[0])
    return wallet_map


def create_debt_action(
    *,
    context,
    messagebox_module,
    kind_label: str,
    debt_label: str,
    contact_entry: ttk.Entry,
    amount_entry: ttk.Entry,
    date_entry: ttk.Entry,
    description_entry: ttk.Entry,
    wallet_var: tk.StringVar,
    wallet_map: dict[str, int],
    refresh: Callable[[], None],
    base_currency_code: Callable[[], str],
) -> None:
    contact = contact_entry.get().strip()
    date_text = date_entry.get().strip()
    description = description_entry.get().strip()
    wallet_id = wallet_map.get(wallet_var.get())
    try:
        amount_base = parse_numeric_input(amount_entry.get().strip())
    except ValueError:
        messagebox_module.showerror(
            tr("common.error", "Ошибка"),
            tr("debts.error.amount_number", "Сумма должна быть числом."),
        )
        return
    if wallet_id is None:
        messagebox_module.showerror(
            tr("common.error", "Ошибка"),
            tr("debts.error.wallet_required", "Кошелек обязателен."),
        )
        return
    if not contact:
        messagebox_module.showerror(
            tr("common.error", "Ошибка"),
            tr("debts.error.contact_required", "Контакт обязателен."),
        )
        return

    kind = DebtKind.DEBT if kind_label == debt_label else DebtKind.LOAN
    try:
        if kind is DebtKind.DEBT:
            context.controller.create_debt(
                contact_name=contact,
                wallet_id=wallet_id,
                amount_base=amount_base,
                created_at=date_text,
                currency=base_currency_code(),
                description=description,
            )
        else:
            context.controller.create_loan(
                contact_name=contact,
                wallet_id=wallet_id,
                amount_base=amount_base,
                created_at=date_text,
                currency=base_currency_code(),
                description=description,
            )
        contact_entry.delete(0, tk.END)
        amount_entry.delete(0, tk.END)
        description_entry.delete(0, tk.END)
        refresh()
        refresh_debts_views(context)
    except (DomainError, ValueError, TypeError, RuntimeError) as error:
        log_ui_error(
            logger,
            "UI_DEBTS_CREATE_FAILED",
            error,
            wallet_id=wallet_id,
            kind=kind.value,
        )
        messagebox_module.showerror(tr("debts.error.create_title", "Ошибка долга"), str(error))


def run_on_selected(
    *,
    context,
    messagebox_module,
    title: str,
    debt_tree: ttk.Treeview,
    action_amount_entry: ttk.Entry,
    action_date_entry: ttk.Entry,
    action_wallet_var: tk.StringVar,
    wallet_map: dict[str, int],
    action: Callable[[Debt, float, str, int | None], None],
    refresh: Callable[[], None],
    wallet_optional: bool = False,
) -> bool:
    debt = selected_debt(context, debt_tree)
    if debt is None:
        messagebox_module.showerror(
            tr("common.error", "Ошибка"),
            tr("debts.error.select_first", "Сначала выберите долг."),
        )
        return False
    date_text = action_date_entry.get().strip()
    try:
        amount_base = parse_numeric_input(action_amount_entry.get().strip())
    except ValueError:
        messagebox_module.showerror(
            tr("common.error", "Ошибка"),
            tr("debts.error.amount_number", "Сумма должна быть числом."),
        )
        return False
    wallet_id = wallet_map.get(action_wallet_var.get())
    if not wallet_optional and wallet_id is None:
        messagebox_module.showerror(
            tr("common.error", "Ошибка"),
            tr("debts.error.wallet_required", "Кошелек обязателен."),
        )
        return False
    wallet_id_arg: int | None = wallet_id
    if not wallet_optional and wallet_id_arg is not None:
        wallet_id_arg = int(wallet_id_arg)
    try:
        action(debt, amount_base, date_text, wallet_id_arg)
        refresh()
        return True
    except (DomainError, ValueError, TypeError, RuntimeError) as error:
        log_ui_error(
            logger,
            "UI_DEBTS_ACTION_FAILED",
            error,
            debt_id=debt.id,
            wallet_id=wallet_id_arg,
        )
        messagebox_module.showerror(title, str(error))
        return False


def close_selected_debt(
    *,
    context,
    messagebox_module,
    debt_tree: ttk.Treeview,
    action_date_entry: ttk.Entry,
    action_wallet_var: tk.StringVar,
    wallet_map: dict[str, int],
    refresh: Callable[[], None],
) -> None:
    debt = selected_debt(context, debt_tree)
    if debt is None:
        messagebox_module.showerror(
            tr("common.error", "Ошибка"),
            tr("debts.error.select_first", "Сначала выберите долг."),
        )
        return
    if debt.remaining_amount_minor <= 0:
        messagebox_module.showerror(
            tr("common.error", "Ошибка"),
            tr("debts.error.already_closed", "Долг уже закрыт."),
        )
        return
    wallet_id = wallet_map.get(action_wallet_var.get())
    if wallet_id is None and debt.kind is DebtKind.DEBT:
        messagebox_module.showerror(
            tr("common.error", "Ошибка"),
            tr("debts.error.wallet_required", "Кошелек обязателен."),
        )
        return
    try:
        context.controller.close_debt(
            debt_id=debt.id,
            payment_date=action_date_entry.get().strip(),
            wallet_id=wallet_id,
            write_off=False,
        )
        refresh()
        refresh_debts_views(context)
    except (DomainError, ValueError, TypeError, RuntimeError) as error:
        log_ui_error(logger, "UI_DEBTS_CLOSE_FAILED", error, debt_id=debt.id)
        messagebox_module.showerror(tr("debts.error.close_title", "Ошибка закрытия"), str(error))


def delete_selected_debt(
    *,
    context,
    messagebox_module,
    debt_tree: ttk.Treeview,
    refresh: Callable[[], None],
) -> None:
    debt = selected_debt(context, debt_tree)
    if debt is None:
        messagebox_module.showerror(
            tr("common.error", "Ошибка"),
            tr("debts.error.select_first", "Сначала выберите долг."),
        )
        return
    if not messagebox_module.askyesno(
        tr("common.confirm", "Подтверждение"),
        tr(
            "debts.confirm.delete",
            "Удалить долг для '{contact}'?\n"
            "\nЭто удалит только карточку долга и историю платежей."
            "\nСвязанные записи доходов/расходов и балансы кошельков останутся без изменений.",
            contact=debt.contact_name,
        ),
    ):
        return
    try:
        context.controller.delete_debt(debt.id)
        refresh()
    except (DomainError, ValueError, TypeError, RuntimeError) as error:
        log_ui_error(logger, "UI_DEBTS_DELETE_FAILED", error, debt_id=debt.id)
        messagebox_module.showerror(tr("debts.error.delete_title", "Ошибка удаления"), str(error))
