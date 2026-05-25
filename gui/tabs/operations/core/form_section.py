"""Creator form section for the operations tab."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass
from tkinter import ttk
from typing import Any

from domain.errors import DomainError
from gui.combobox_compat import enable_wayland_combobox_support
from gui.i18n import tr
from gui.logging_utils import log_ui_error
from gui.ui_helpers import show_error, show_info
from gui.ui_theme import create_card_section
from utils.records.tags import (
    TAG_COLOR_PALETTE,
    find_numeric_only_tags,
    normalize_tag_name,
    parse_tag_string,
)

from ..support.form_support import (
    active_tag_name,
    bind_focus_navigation,
    build_basic_form_fields,
    build_tag_widgets,
    build_wallet_widgets,
    create_form_label_builder,
)
from .contracts import OperationsTabContext
from .tag_input import (
    attach_tag_autocomplete,
    list_tags_safe,
    sorted_tags_by_popularity,
    split_tag_input,
)


@dataclass(slots=True)
class OperationFormSection:
    type_combo: ttk.Combobox
    refresh_category_combo: Callable[[], None]
    refresh_operation_wallet_menu: Callable[[], None]
    set_type_income: Callable[[], None]
    set_type_expense: Callable[[], None]
    save_record: Callable[[], None]
    base_currency_code: Callable[[], str]
    is_kzt_currency: Callable[[object], bool]
    amount_edit_label_text: Callable[[object], str]
    amount_edit_tooltip_text: str
    sync_tag_color_from_input: Callable[[], None]


def build_operation_form_section(
    parent: ttk.PanedWindow,
    *,
    context: OperationsTabContext,
    logger: Any,
    on_saved: Callable[[], None],
) -> OperationFormSection:
    form_card = create_card_section(parent, tr("operations.new", "Новая операция"))
    parent.add(form_card, weight=1)
    form_frame = form_card.winfo_children()[-1]
    form_frame.grid_columnconfigure(1, weight=1)
    form_frame.grid_columnconfigure(2, weight=1)
    form_frame.grid_columnconfigure(3, weight=0)

    label_width = 12
    _form_label = create_form_label_builder(form_frame, label_width=label_width)

    def _base_currency_code() -> str:
        getter = getattr(context.controller, "get_base_currency_code", None)
        if callable(getter):
            return str(getter() or "").strip().upper() or "KZT"
        return "KZT"

    def _is_kzt_currency(value: object) -> bool:
        return str(value or _base_currency_code()).strip().upper() == _base_currency_code()

    def _amount_edit_label_text(currency: object) -> str:
        if _is_kzt_currency(currency):
            return tr("common.amount", "Сумма:")
        return tr("operations.edit.amount_equivalent", "Эквивалент в валюте базы:")

    amount_edit_tooltip_text = tr(
        "operations.edit.amount_tooltip",
        "Для операций в валюте базы это основная сумма операции."
        "\nДля других валют это эквивалент в валюте базы и он влияет на курс операции.",
    )

    income_label = tr("operations.type.income", "Доход")
    expense_label = tr("operations.type.expense", "Расход")
    basic_fields = build_basic_form_fields(
        form_frame=form_frame,
        form_label=_form_label,
        enable_combobox_support=enable_wayland_combobox_support,
        income_label=income_label,
        base_currency_code=_base_currency_code(),
    )
    type_combo = basic_fields["type_combo"]
    date_entry = basic_fields["date_entry"]
    amount_entry = basic_fields["amount_entry"]
    currency_entry = basic_fields["currency_entry"]
    category_combo = basic_fields["category_combo"]
    description_entry = basic_fields["description_entry"]

    tags_combo, tag_color_button, selected_tag_color, color_popup_state, palette = (
        build_tag_widgets(
            form_frame=form_frame,
            form_label=_form_label,
        )
    )

    operation_wallet_var, operation_wallet_menu, operation_wallet_map = build_wallet_widgets(
        form_frame=form_frame,
        form_label=_form_label,
        enable_combobox_support=enable_wayland_combobox_support,
    )

    def _set_tag_color(color: str) -> None:
        normalized = str(color or "").strip() or TAG_COLOR_PALETTE[0]
        selected_tag_color["value"] = normalized
        tag_color_button.configure(
            bg=normalized,
            activebackground=normalized,
            highlightbackground=palette.border_soft,
        )

    def _next_free_color() -> str:
        used_colors = {
            str(getattr(tag, "color", "") or "") for tag in list_tags_safe(context.controller)
        }
        for color in TAG_COLOR_PALETTE:
            if color not in used_colors:
                return color
        return TAG_COLOR_PALETTE[0]

    def _sync_tag_color_from_input() -> None:
        committed, fragment = split_tag_input(tags_combo.get())
        normalized_fragment = normalize_tag_name(fragment)
        tags_by_name = {
            str(getattr(tag, "name", "") or ""): tag for tag in list_tags_safe(context.controller)
        }
        if normalized_fragment and normalized_fragment in tags_by_name:
            _set_tag_color(
                str(getattr(tags_by_name[normalized_fragment], "color", "") or _next_free_color())
            )
            return
        if committed:
            last_tag = tags_by_name.get(committed[-1])
            if last_tag is not None:
                _set_tag_color(str(getattr(last_tag, "color", "") or _next_free_color()))
                return
        _set_tag_color(_next_free_color())

    def _hide_color_popup(_event: object | None = None) -> None:
        menu = color_popup_state.get("menu")
        if menu is not None:
            try:
                menu.unpost()
            except tk.TclError:
                pass
            else:
                form_frame.after_idle(lambda current=menu: current.destroy())
        color_popup_state["menu"] = None
        form_frame.after(0, tags_combo.focus_set)

    def _select_tag_color(color: str) -> None:
        _set_tag_color(color)
        _hide_color_popup()

    def _show_color_popup() -> None:
        if color_popup_state.get("menu") is not None:
            _hide_color_popup()
            return
        _hide_color_popup()
        popup = tk.Menu(
            form_frame,
            tearoff=False,
            relief="solid",
            borderwidth=1,
            activeborderwidth=0,
            bg=palette.surface_elevated,
            fg=palette.text_primary,
        )
        for color in TAG_COLOR_PALETTE:
            popup.add_command(
                label=color,
                background=color,
                activebackground=color,
                command=lambda selected=color: _select_tag_color(selected),
            )
        x = tag_color_button.winfo_rootx()
        y = tag_color_button.winfo_rooty() + tag_color_button.winfo_height() + 2
        color_popup_state["menu"] = popup
        popup.post(x, y)

    def _refresh_category_combo() -> None:
        try:
            if type_combo.get() == income_label:
                category_combo["values"] = context.controller.get_income_categories()
            else:
                category_combo["values"] = context.controller.get_expense_categories()
        except (ValueError, RuntimeError):
            pass
        category_combo.set("General")

    def _on_type_change(*_args: object) -> None:
        _refresh_category_combo()

    def _set_type_income() -> None:
        type_combo.set(income_label)
        _on_type_change()

    def _set_type_expense() -> None:
        type_combo.set(expense_label)
        _on_type_change()

    def refresh_operation_wallet_menu() -> None:
        nonlocal operation_wallet_map
        wallets = context.controller.load_active_wallets()
        operation_wallet_map = {
            f"[{wallet.id}] {wallet.name} ({wallet.currency})": wallet.id for wallet in wallets
        }
        labels = list(operation_wallet_map.keys()) or [""]
        operation_wallet_menu["values"] = labels
        if operation_wallet_var.get() not in operation_wallet_map:
            operation_wallet_var.set(labels[0])

    refresh_operation_wallet_menu()
    _sync_tag_color_from_input()
    attach_tag_autocomplete(
        owner=form_frame,
        combobox=tags_combo,
        list_tags=lambda: sorted_tags_by_popularity(context.controller),
        on_input_changed=_sync_tag_color_from_input,
    )
    tag_color_button.configure(command=_show_color_popup)
    tag_color_button.bind("<Return>", lambda _event: (_show_color_popup(), "break")[1], add="+")
    tag_color_button.bind("<space>", lambda _event: (_show_color_popup(), "break")[1], add="+")

    def save_record() -> None:
        date_str = date_entry.get().strip()
        if not date_str:
            show_error(tr("operations.error.date_required", "Укажите дату."))
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

        amount_str = amount_entry.get().strip()
        if not amount_str:
            show_error(tr("operations.error.amount_required", "Укажите сумму."))
            return
        try:
            amount = float(amount_str)
        except ValueError:
            show_error(tr("operations.error.amount_number", "Сумма должна быть числом."))
            return

        currency = (currency_entry.get() or _base_currency_code()).strip()
        category = (category_combo.get() or "General").strip()
        description = description_entry.get().strip()
        raw_tags = tags_combo.get().strip()
        invalid_tags = find_numeric_only_tags(raw_tags)
        if invalid_tags:
            show_error(
                tr(
                    "operations.error.invalid_tag_numeric",
                    "Тег не должен состоять только из цифр: {tags}",
                    tags=", ".join(f'"{tag}"' for tag in invalid_tags),
                )
            )
            return
        tags = parse_tag_string(raw_tags)
        wallet_id = operation_wallet_map.get(operation_wallet_var.get())
        if wallet_id is None:
            show_error(tr("operations.error.wallet_required", "Выберите кошелек."))
            return

        try:
            if type_combo.get() == income_label:
                context.controller.create_income(
                    date=date_str,
                    wallet_id=wallet_id,
                    amount=amount,
                    currency=currency,
                    category=category,
                    description=description,
                    tags=tags,
                )
                show_info(tr("operations.save_success.income", "Доход успешно добавлен."))
            else:
                context.controller.create_expense(
                    date=date_str,
                    wallet_id=wallet_id,
                    amount=amount,
                    currency=currency,
                    category=category,
                    description=description,
                    tags=tags,
                )
                show_info(tr("operations.save_success.expense", "Расход успешно добавлен."))

            existing_tags = {
                str(getattr(tag, "name", "") or ""): str(getattr(tag, "color", "") or "")
                for tag in list_tags_safe(context.controller)
            }
            chosen_tag_name = active_tag_name(raw_tags, tags)
            if chosen_tag_name and chosen_tag_name in tags:
                context.controller.set_tag_color(chosen_tag_name, selected_tag_color["value"])
            for tag_name in tags:
                if tag_name != chosen_tag_name and not existing_tags.get(tag_name):
                    context.controller.set_tag_color(tag_name, selected_tag_color["value"])

            amount_entry.delete(0, tk.END)
            category_combo.delete(0, tk.END)
            description_entry.delete(0, tk.END)
            tags_combo.delete(0, tk.END)
            _refresh_category_combo()
            _sync_tag_color_from_input()
            on_saved()
        except (DomainError, ValueError, TypeError, RuntimeError) as error:
            log_ui_error(logger, "UI_OPS_CREATE_RECORD_FAILED", error, wallet_id=wallet_id)
            show_error(
                tr(
                    "operations.error.save_failed",
                    "Не удалось сохранить операцию: {error}",
                    error=error,
                )
            )

    creator_widgets = [
        date_entry,
        amount_entry,
        currency_entry,
        category_combo,
        description_entry,
        tags_combo,
        operation_wallet_menu,
    ]
    save_button = ttk.Button(
        form_frame,
        text=tr("common.save", "Сохранить"),
        style="Primary.TButton",
        command=save_record,
    )
    save_button.grid(row=8, column=0, columnspan=4, pady=8)
    bind_focus_navigation([*creator_widgets, save_button], submit_action=save_record)

    type_combo.bind("<<ComboboxSelected>>", _on_type_change)
    _refresh_category_combo()

    return OperationFormSection(
        type_combo=type_combo,
        refresh_category_combo=_refresh_category_combo,
        refresh_operation_wallet_menu=refresh_operation_wallet_menu,
        set_type_income=_set_type_income,
        set_type_expense=_set_type_expense,
        save_record=save_record,
        base_currency_code=_base_currency_code,
        is_kzt_currency=_is_kzt_currency,
        amount_edit_label_text=_amount_edit_label_text,
        amount_edit_tooltip_text=amount_edit_tooltip_text,
        sync_tag_color_from_input=_sync_tag_color_from_input,
    )
