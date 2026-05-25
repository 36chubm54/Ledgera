"""Transfer creator section for the operations tab."""

from __future__ import annotations

import logging
import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass
from tkinter import ttk

from domain.errors import DomainError
from gui.combobox_compat import enable_wayland_combobox_support
from gui.i18n import tr
from gui.logging_utils import log_ui_error
from gui.ui_helpers import show_error, show_info
from gui.ui_theme import create_card_section

from ..support.transfer_support import bind_transfer_focus_navigation, build_transfer_fields
from .contracts import OperationsTabContext


@dataclass(slots=True)
class TransferSection:
    refresh_transfer_wallet_menus: Callable[[], None]
    create_transfer: Callable[[], None]


def build_transfer_section(
    parent: ttk.PanedWindow,
    *,
    context: OperationsTabContext,
    logger: logging.Logger,
    base_currency_code: Callable[[], str],
    on_saved: Callable[[], None],
) -> TransferSection:
    wallet_id_map: dict[str, int] = {}

    transfer_card = create_card_section(
        parent,
        tr("operations.transfer", "Перевод между кошельками"),
    )
    parent.add(transfer_card, weight=1)
    transfer_frame = transfer_card.winfo_children()[-1]
    transfer_frame.grid_columnconfigure(1, weight=1)
    widgets = build_transfer_fields(
        transfer_frame=transfer_frame,
        enable_combobox_support=enable_wayland_combobox_support,
        base_currency_code=base_currency_code(),
    )
    transfer_from_var = widgets["transfer_from_var"]
    transfer_from_menu = widgets["transfer_from_menu"]
    transfer_to_var = widgets["transfer_to_var"]
    transfer_to_menu = widgets["transfer_to_menu"]
    transfer_date_entry = widgets["transfer_date_entry"]
    transfer_amount_entry = widgets["transfer_amount_entry"]
    transfer_currency_entry = widgets["transfer_currency_entry"]
    transfer_commission_entry = widgets["transfer_commission_entry"]
    transfer_commission_currency_entry = widgets["transfer_commission_currency_entry"]
    transfer_description_entry = widgets["transfer_description_entry"]

    def refresh_transfer_wallet_menus() -> None:
        nonlocal wallet_id_map
        wallets = context.controller.load_active_wallets()
        wallet_id_map = {
            f"[{wallet.id}] {wallet.name} ({wallet.currency})": wallet.id for wallet in wallets
        }
        labels = list(wallet_id_map.keys()) or [""]

        for combo_widget, var in (
            (transfer_from_menu, transfer_from_var),
            (transfer_to_menu, transfer_to_var),
        ):
            combo_widget["values"] = labels
            if not var.get() or var.get() not in wallet_id_map:
                var.set(labels[0])

        if len(labels) > 1 and transfer_to_var.get() == transfer_from_var.get():
            transfer_to_var.set(labels[1])

    def create_transfer() -> None:
        from_wallet_id = wallet_id_map.get(transfer_from_var.get())
        to_wallet_id = wallet_id_map.get(transfer_to_var.get())
        if from_wallet_id is None or to_wallet_id is None:
            show_error(
                tr(
                    "operations.transfer.error.wallets_required",
                    "Выберите кошелек отправителя и получателя.",
                )
            )
            return

        date_str = transfer_date_entry.get().strip()
        if not date_str:
            show_error(tr("operations.transfer.error.date_required", "Укажите дату перевода."))
            return
        try:
            from domain.validation import ensure_not_future, parse_ymd

            entered_date = parse_ymd(date_str)
            ensure_not_future(entered_date)
        except ValueError as error:
            show_error(
                tr(
                    "operations.error.invalid_date",
                    "Некорректная дата: {error}. Используйте формат ГГГГ-ММ-ДД.",
                    error=error,
                )
            )
            return

        amount_str = transfer_amount_entry.get().strip()
        if not amount_str:
            show_error(tr("operations.transfer.error.amount_required", "Укажите сумму перевода."))
            return

        try:
            transfer_amount = float(amount_str)
            commission_amount = float((transfer_commission_entry.get() or "0").strip())
        except ValueError:
            show_error(
                tr(
                    "operations.transfer.error.amount_number",
                    "Сумма перевода и комиссия должны быть числами.",
                )
            )
            return

        try:
            transfer_id = context.controller.create_transfer(
                from_wallet_id=from_wallet_id,
                to_wallet_id=to_wallet_id,
                transfer_date=date_str,
                amount=transfer_amount,
                currency=(transfer_currency_entry.get() or base_currency_code()).strip(),
                description=transfer_description_entry.get().strip(),
                commission_amount=commission_amount,
                commission_currency=(transfer_commission_currency_entry.get() or "").strip(),
            )
            show_info(
                tr("operations.transfer.created", "Перевод создан (id={id}).", id=transfer_id)
            )
            transfer_amount_entry.delete(0, tk.END)
            transfer_description_entry.delete(0, tk.END)
            transfer_commission_entry.delete(0, tk.END)
            transfer_commission_entry.insert(0, "0")
            on_saved()
        except (DomainError, ValueError, TypeError, RuntimeError) as error:
            log_ui_error(
                logger,
                "UI_OPS_CREATE_TRANSFER_FAILED",
                error,
                from_wallet_id=from_wallet_id,
                to_wallet_id=to_wallet_id,
            )
            show_error(
                tr(
                    "operations.transfer.error.create_failed",
                    "Не удалось создать перевод: {error}",
                    error=error,
                )
            )

    transfer_creator_widgets = [
        transfer_from_menu,
        transfer_to_menu,
        transfer_date_entry,
        transfer_amount_entry,
        transfer_currency_entry,
        transfer_commission_entry,
        transfer_commission_currency_entry,
        transfer_description_entry,
    ]
    transfer_create_button = ttk.Button(
        transfer_card,
        text=tr("operations.transfer.create", "Создать перевод"),
        command=create_transfer,
        style="Primary.TButton",
    )
    transfer_create_button.grid(row=8, column=0, columnspan=2, pady=6)
    bind_transfer_focus_navigation(
        [*transfer_creator_widgets, transfer_create_button], submit_action=create_transfer
    )
    refresh_transfer_wallet_menus()

    return TransferSection(
        refresh_transfer_wallet_menus=refresh_transfer_wallet_menus,
        create_transfer=create_transfer,
    )
