from __future__ import annotations

import logging
import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from domain.errors import DomainError
from gui.i18n import tr
from gui.logging_utils import log_ui_error

logger = logging.getLogger(__name__)


class MessageBoxLike(Protocol):
    def showerror(self, title: str, message: str) -> Any: ...

    def showinfo(self, title: str, message: str) -> Any: ...

    def askyesno(self, title: str, message: str) -> bool: ...


@dataclass(slots=True)
class WalletFormFields:
    name_entry: Any
    currency_entry: Any
    initial_entry: Any
    allow_negative_var: tk.BooleanVar


class WalletFormLike(Protocol):
    name_entry: Any
    currency_entry: Any
    initial_entry: Any
    allow_negative_var: tk.BooleanVar


def refresh_wallet_related_ui(context: Any) -> None:
    if context.refresh_transfer_wallet_menus is not None:
        try:
            context.refresh_transfer_wallet_menus()
        except tk.TclError:
            pass

    if context.refresh_operation_wallet_menu is not None:
        try:
            context.refresh_operation_wallet_menu()
        except tk.TclError:
            pass


def refresh_wallet_tree(wallet_tree: Any, context: Any) -> None:
    for iid in wallet_tree.get_children():
        wallet_tree.delete(iid)
    active_balances = {
        int(balance.wallet_id): float(balance.balance)
        for balance in context.controller.get_wallet_balances()
    }
    for wallet in context.controller.load_wallets():
        balance = active_balances.get(int(wallet.id))
        if balance is None:
            try:
                balance = context.controller.wallet_balance(wallet.id)
            except ValueError:
                balance = wallet.initial_balance
        wallet_tree.insert(
            "",
            tk.END,
            values=(
                int(wallet.id),
                str(wallet.name),
                str(wallet.currency),
                f"{wallet.initial_balance:.2f}",
                f"{balance:.2f}",
                tr("common.yes", "Да") if wallet.allow_negative else tr("common.no", "Нет"),
                tr("common.yes", "Да") if wallet.is_active else tr("common.no", "Нет"),
            ),
        )
    refresh_wallet_related_ui(context)


def create_wallet_action(
    *,
    context: Any,
    form_fields: WalletFormLike,
    base_currency_code: str,
    messagebox_module: MessageBoxLike,
    refresh_wallets: Callable[[], None],
) -> None:
    try:
        initial_balance = float(form_fields.initial_entry.get().strip() or "0")
    except ValueError:
        messagebox_module.showerror(
            tr("common.error", "Ошибка"),
            tr(
                "settings.wallets.error.initial_balance",
                "Некорректный начальный баланс кошелька.",
            ),
        )
        return

    name = ""
    try:
        name = form_fields.name_entry.get().strip()
        wallet = context.controller.create_wallet(
            name=name,
            currency=(form_fields.currency_entry.get() or base_currency_code).strip(),
            initial_balance=initial_balance,
            allow_negative=form_fields.allow_negative_var.get(),
        )
        messagebox_module.showinfo(
            tr("common.done", "Готово"),
            tr(
                "settings.wallets.created",
                "Кошелек создан: [{wallet_id}] {wallet_name}",
                wallet_id=wallet.id,
                wallet_name=wallet.name,
            ),
        )
        form_fields.name_entry.delete(0, tk.END)
        form_fields.initial_entry.delete(0, tk.END)
        form_fields.initial_entry.insert(0, "0")
        refresh_wallets()
    except (DomainError, ValueError, TypeError, RuntimeError) as error:
        log_ui_error(logger, "UI_SETTINGS_CREATE_WALLET_FAILED", error, name=name)
        messagebox_module.showerror(
            tr("common.error", "Ошибка"),
            tr(
                "settings.wallets.error.create",
                "Не удалось создать кошелек: {error}",
                error=str(error),
            ),
        )


def delete_wallet_action(
    *,
    wallet_tree: Any,
    context: Any,
    messagebox_module: MessageBoxLike,
    refresh_wallets: Callable[[], None],
) -> None:
    selection = wallet_tree.selection()
    if not selection:
        messagebox_module.showerror(
            tr("common.error", "Ошибка"),
            tr("settings.wallets.error.select_delete", "Выберите кошелек для удаления."),
        )
        return
    try:
        values = wallet_tree.item(selection[0], "values")
        wallet_id = int(values[0])
    except (TypeError, ValueError, IndexError):
        messagebox_module.showerror(
            tr("common.error", "Ошибка"),
            tr(
                "settings.wallets.error.parse_id",
                "Не удалось определить идентификатор выбранного кошелька.",
            ),
        )
        return

    try:
        context.controller.soft_delete_wallet(wallet_id)
        messagebox_module.showinfo(
            tr("common.done", "Готово"),
            tr("settings.wallets.deleted", "Кошелек деактивирован."),
        )
        refresh_wallets()
    except (DomainError, ValueError, TypeError, RuntimeError) as error:
        log_ui_error(logger, "UI_SETTINGS_DELETE_WALLET_FAILED", error, wallet_id=wallet_id)
        messagebox_module.showerror(tr("common.error", "Ошибка"), str(error))
