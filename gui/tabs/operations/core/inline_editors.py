"""Inline editors for records and transfers in the operations tab."""

from __future__ import annotations

import logging
import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass
from tkinter import ttk
from typing import Any

from domain.errors import DomainError
from gui.i18n import tr
from gui.logging_utils import log_ui_error
from gui.ui_helpers import safe_destroy, show_error, show_info
from utils.records.tags import find_numeric_only_tags

from ..support.inline_support import (
    bind_inline_editor_navigation,
    build_inline_action_buttons,
    build_record_editor_widgets,
    build_transfer_editor_widgets,
    create_inline_panel,
    date_text,
)
from .contracts import OperationsTabContext
from .tag_input import attach_tag_autocomplete, sorted_tags_by_popularity


@dataclass(slots=True)
class InlineEditors:
    edit_selected_record_inline: Callable[[], None]
    edit_selected_transfer_inline: Callable[[int], None]
    inline_editor_active: Callable[[], bool]


def build_inline_editors(
    *,
    list_frame: ttk.Frame,
    records_tree: ttk.Treeview,
    context: OperationsTabContext,
    logger: logging.Logger,
    refresh_category_combo: Callable[[], None],
    sync_tag_color_from_input: Callable[[], None],
    base_currency_code: Callable[[], str],
    is_kzt_currency: Callable[[object], bool],
    amount_edit_label_text: Callable[[object], str],
    amount_edit_tooltip_text: str,
    after_update: Callable[[], None],
) -> InlineEditors:
    edit_panel_state: dict[str, Any] = {"panel": None}

    def inline_editor_active() -> bool:
        panel = edit_panel_state.get("panel")
        if panel is None:
            return False
        try:
            return bool(panel.winfo_exists())
        except (tk.TclError, RuntimeError, AttributeError):
            return False

    def edit_selected_transfer_inline(transfer_id: int) -> None:
        try:
            transfer = context.controller.get_transfer_for_edit(transfer_id)
        except (ValueError, TypeError, RuntimeError):
            show_error(
                tr(
                    "operations.transfer.error.edit_load_failed",
                    "Не удалось загрузить перевод для редактирования.",
                )
            )
            return

        if edit_panel_state["panel"] is not None:
            try:
                edit_panel_state["panel"].destroy()
            except (tk.TclError, RuntimeError):
                pass
            edit_panel_state["panel"] = None

        edit_panel = create_inline_panel(list_frame=list_frame, row=4)
        edit_panel_state["panel"] = edit_panel
        widgets = build_transfer_editor_widgets(
            edit_panel=edit_panel,
            transfer=transfer,
            base_currency_code=base_currency_code,
            amount_edit_label_text=amount_edit_label_text,
            amount_edit_tooltip_text=amount_edit_tooltip_text,
        )
        date_edit_entry = widgets["date_edit_entry"]
        amount_base_edit_entry = widgets["amount_base_edit_entry"]
        from_wallet_var = widgets["from_wallet_var"]
        from_wallet_menu = widgets["from_wallet_menu"]
        to_wallet_var = widgets["to_wallet_var"]
        to_wallet_menu = widgets["to_wallet_menu"]
        description_edit_entry = widgets["description_edit_entry"]

        date_value = date_text(transfer.date)
        date_edit_entry.insert(0, date_value)
        if is_kzt_currency(getattr(transfer, "currency", base_currency_code())):
            amount_value = float(transfer.amount_original or transfer.amount_base or 0.0)
        else:
            amount_value = float(transfer.amount_base or 0.0)
        amount_base_edit_entry.insert(0, f"{amount_value:.2f}")
        description_edit_entry.insert(0, transfer.description)

        wallet_edit_map: dict[str, int] = {
            f"[{wallet.id}] {wallet.name} ({wallet.currency})": wallet.id
            for wallet in context.controller.load_active_wallets()
        }
        wallet_labels = list(wallet_edit_map.keys()) or [""]
        from_wallet_menu["values"] = wallet_labels
        to_wallet_menu["values"] = wallet_labels
        from_wallet_var.set(
            next(
                (
                    label
                    for label, wallet_id in wallet_edit_map.items()
                    if int(wallet_id) == int(transfer.from_wallet_id)
                ),
                wallet_labels[0],
            )
        )
        to_wallet_var.set(
            next(
                (
                    label
                    for label, wallet_id in wallet_edit_map.items()
                    if int(wallet_id) == int(transfer.to_wallet_id)
                ),
                wallet_labels[0],
            )
        )

        def cancel_edit() -> None:
            if edit_panel_state["panel"] is not None:
                safe_destroy(edit_panel_state["panel"])
                edit_panel_state["panel"] = None

        def save_edit() -> None:
            new_date = date_edit_entry.get().strip()
            if not new_date:
                show_error(tr("operations.transfer.error.date_required", "Укажите дату перевода."))
                return
            try:
                new_amount_base = float(amount_base_edit_entry.get().strip())
            except ValueError:
                show_error(tr("operations.error.amount_number", "Сумма должна быть числом."))
                return
            new_from_wallet_id = wallet_edit_map.get(from_wallet_var.get())
            new_to_wallet_id = wallet_edit_map.get(to_wallet_var.get())
            if new_from_wallet_id is None or new_to_wallet_id is None:
                show_error(
                    tr(
                        "operations.transfer.error.wallets_required",
                        "Выберите кошелек отправителя и получателя.",
                    )
                )
                return
            try:
                context.controller.update_transfer_inline(
                    transfer_id,
                    new_date=new_date,
                    new_from_wallet_id=new_from_wallet_id,
                    new_to_wallet_id=new_to_wallet_id,
                    new_description=description_edit_entry.get().strip(),
                    new_amount_base=new_amount_base,
                )
                show_info(tr("operations.transfer.updated", "Перевод обновлен."))
                after_update()
                cancel_edit()
            except (DomainError, ValueError, TypeError, RuntimeError) as error:
                log_ui_error(
                    logger,
                    "UI_OPS_EDIT_TRANSFER_FAILED",
                    error,
                    transfer_id=transfer_id,
                    new_from_wallet_id=new_from_wallet_id,
                    new_to_wallet_id=new_to_wallet_id,
                    new_amount_base=new_amount_base,
                )
                show_error(
                    tr(
                        "operations.transfer.error.update_failed",
                        "Не удалось обновить перевод: {error}",
                        error=error,
                    )
                )

        save_button, cancel_button = build_inline_action_buttons(
            edit_panel=edit_panel,
            row=5,
            on_save=save_edit,
            on_cancel=cancel_edit,
        )
        for widget in (
            date_edit_entry,
            amount_base_edit_entry,
            from_wallet_menu,
            to_wallet_menu,
            description_edit_entry,
            save_button,
            cancel_button,
        ):
            widget.bind("<Escape>", lambda _event: (cancel_edit(), "break")[1], add="+")
        date_edit_entry.bind("<Return>", lambda _event: (save_edit(), "break")[1], add="+")
        amount_base_edit_entry.bind("<Return>", lambda _event: (save_edit(), "break")[1], add="+")
        to_wallet_menu.bind("<Return>", lambda _event: (save_edit(), "break")[1], add="+")
        description_edit_entry.bind("<Return>", lambda _event: (save_edit(), "break")[1], add="+")
        date_edit_entry.focus_set()
        date_edit_entry.selection_range(0, tk.END)

    def edit_selected_record_inline() -> None:
        selection = records_tree.selection()
        if not selection:
            show_error(tr("operations.error.select_first", "Сначала выберите запись."))
            return

        ui_record_id = selection[0]
        domain_record_id = context._record_id_to_domain_id.get(ui_record_id)
        if domain_record_id is None:
            show_error(tr("operations.error.edit_forbidden", "Эту запись нельзя редактировать."))
            return

        try:
            record = context.controller.get_record_for_edit(domain_record_id)
        except (ValueError, TypeError, RuntimeError):
            show_error(
                tr(
                    "operations.error.edit_load_failed",
                    "Не удалось загрузить запись для редактирования.",
                )
            )
            return

        if record.transfer_id is not None:
            edit_selected_transfer_inline(int(record.transfer_id))
            return
        if str(getattr(record, "category", "") or "").strip().lower() == "transfer":
            show_error(
                tr(
                    "operations.error.transfer_row_edit_forbidden",
                    "Строки перевода редактировать нельзя.",
                )
            )
            return

        if edit_panel_state["panel"] is not None:
            try:
                edit_panel_state["panel"].destroy()
            except (tk.TclError, RuntimeError):
                pass
            edit_panel_state["panel"] = None

        edit_panel = create_inline_panel(list_frame=list_frame, row=3)
        edit_panel_state["panel"] = edit_panel
        widgets = build_record_editor_widgets(
            edit_panel=edit_panel,
            record=record,
            base_currency_code=base_currency_code,
            amount_edit_label_text=amount_edit_label_text,
            amount_edit_tooltip_text=amount_edit_tooltip_text,
        )
        amount_entry = widgets["amount_entry"]
        date_edit_entry = widgets["date_edit_entry"]
        wallet_edit_var = widgets["wallet_edit_var"]
        wallet_edit_menu = widgets["wallet_edit_menu"]
        category_edit_combo = widgets["category_edit_combo"]
        description_edit_entry = widgets["description_edit_entry"]
        tags_edit_combo = widgets["tags_edit_combo"]

        if is_kzt_currency(getattr(record, "currency", base_currency_code())):
            amount_value = float(record.amount_original or record.amount_base or 0.0)
        else:
            amount_value = float(record.amount_base or 0.0)
        amount_entry.insert(0, f"{amount_value:.2f}")
        date_value = date_text(record.date)
        date_edit_entry.insert(0, date_value)
        try:
            if record.type == "income":
                category_edit_combo["values"] = context.controller.get_income_categories()
            elif record.type == "expense":
                category_edit_combo["values"] = context.controller.get_expense_categories()
            else:
                category_edit_combo["values"] = (
                    context.controller.get_mandatory_expense_categories()
                )
        except (ValueError, RuntimeError):
            pass
        category_edit_combo.insert(0, str(record.category or ""))
        description_edit_entry.insert(0, str(record.description or ""))
        tags_edit_combo.insert(0, ", ".join(tuple(getattr(record, "tags", ()) or ())))
        attach_tag_autocomplete(
            owner=edit_panel,
            combobox=tags_edit_combo,
            list_tags=lambda: sorted_tags_by_popularity(context.controller),
        )

        wallet_edit_map: dict[str, int] = {
            f"[{wallet.id}] {wallet.name} ({wallet.currency})": wallet.id
            for wallet in context.controller.load_wallets()
        }
        wallet_labels = list(wallet_edit_map.keys()) or [""]
        wallet_edit_menu["values"] = wallet_labels
        current_wallet_label = next(
            (label for label, wid in wallet_edit_map.items() if int(wid) == int(record.wallet_id)),
            wallet_labels[0],
        )
        wallet_edit_var.set(current_wallet_label)

        def save_edit() -> None:
            try:
                new_amount_base = float(amount_entry.get().strip())
            except ValueError:
                show_error(tr("operations.error.amount_number", "Сумма должна быть числом."))
                return
            new_date = date_edit_entry.get().strip()
            if not new_date:
                show_error(tr("operations.error.date_required", "Укажите дату."))
                return
            new_category = category_edit_combo.get().strip()
            if not new_category:
                show_error(tr("operations.error.category_required", "Укажите категорию."))
                return
            new_wallet_id = wallet_edit_map.get(wallet_edit_var.get())
            if new_wallet_id is None:
                show_error(tr("operations.error.wallet_required", "Выберите кошелек."))
                return
            invalid_tags = find_numeric_only_tags(tags_edit_combo.get().strip())
            if invalid_tags:
                show_error(
                    tr(
                        "operations.error.invalid_tag_numeric",
                        "Тег не должен состоять только из цифр: {tags}",
                        tags=", ".join(f'"{tag}"' for tag in invalid_tags),
                    )
                )
                return
            try:
                context.controller.update_record_inline(
                    domain_record_id,
                    new_amount_base=new_amount_base,
                    new_category=new_category,
                    new_description=description_edit_entry.get().strip(),
                    new_date=new_date,
                    new_wallet_id=new_wallet_id,
                    new_tags=tags_edit_combo.get().strip(),
                )
                show_info(tr("operations.updated", "Запись обновлена."))
                sync_tag_color_from_input()
                after_update()
                cancel_edit()
            except (DomainError, ValueError, TypeError, RuntimeError) as error:
                log_ui_error(
                    logger,
                    "UI_OPS_EDIT_RECORD_FAILED",
                    error,
                    record_id=domain_record_id,
                    new_wallet_id=new_wallet_id,
                )
                show_error(
                    tr(
                        "operations.error.update_failed",
                        "Не удалось обновить запись: {error}",
                        error=error,
                    )
                )

        def cancel_edit() -> None:
            if edit_panel_state["panel"] is not None:
                safe_destroy(edit_panel_state["panel"])
                edit_panel_state["panel"] = None

        save_button, cancel_button = build_inline_action_buttons(
            edit_panel=edit_panel,
            row=6,
            on_save=save_edit,
            on_cancel=cancel_edit,
        )

        navigation_widgets: list[tk.Misc] = [
            amount_entry,
            date_edit_entry,
            wallet_edit_menu,
            category_edit_combo,
            description_edit_entry,
            tags_edit_combo,
            save_button,
            cancel_button,
        ]
        bind_inline_editor_navigation(
            navigation_widgets,
            on_save=save_edit,
            on_cancel=cancel_edit,
        )

        amount_entry.focus_set()

    return InlineEditors(
        edit_selected_record_inline=edit_selected_record_inline,
        edit_selected_transfer_inline=edit_selected_transfer_inline,
        inline_editor_active=inline_editor_active,
    )
