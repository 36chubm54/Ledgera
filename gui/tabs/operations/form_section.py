"""Creator form section for the operations tab."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from tkinter import ttk
from typing import Any

from domain.errors import DomainError
from gui.i18n import tr
from gui.logging_utils import log_ui_error
from gui.tooltip import Tooltip
from gui.ui_helpers import show_error, show_info
from gui.ui_theme import PAD_SM, PAD_XS, create_card_section, get_palette
from utils.tag_utils import (
    TAG_COLOR_PALETTE,
    find_numeric_only_tags,
    normalize_tag_name,
    parse_tag_string,
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

    def _form_label(row: int, text: str) -> ttk.Label:
        label = ttk.Label(
            form_frame,
            text=text,
            width=label_width,
            anchor="w",
            style="FormField.TLabel",
        )
        label.grid(row=row, column=0, sticky="w", padx=PAD_SM, pady=PAD_XS)
        return label

    palette = get_palette()

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
    _form_label(0, tr("common.type", "Тип:"))
    type_options = [income_label, expense_label]
    type_combo = ttk.Combobox(form_frame, values=type_options, state="readonly")
    type_combo.set(income_label)
    type_combo.grid(row=0, column=1, columnspan=3, sticky="ew", padx=PAD_SM, pady=PAD_XS)

    _form_label(1, tr("common.date", "Дата:"))
    date_entry = ttk.Entry(form_frame)
    date_entry.grid(row=1, column=1, columnspan=3, sticky="ew", padx=PAD_SM, pady=PAD_XS)
    date_entry.insert(0, date.today().isoformat())

    _form_label(2, tr("common.amount", "Сумма:"))
    amount_entry = ttk.Entry(form_frame)
    amount_entry.grid(row=2, column=1, columnspan=3, sticky="ew", padx=PAD_SM, pady=PAD_XS)

    _form_label(3, tr("common.currency", "Валюта:"))
    currency_entry = ttk.Entry(form_frame)
    currency_entry.insert(0, _base_currency_code())
    currency_entry.grid(row=3, column=1, columnspan=3, sticky="ew", padx=PAD_SM, pady=PAD_XS)

    _form_label(4, tr("common.category", "Категория:"))
    category_combo = ttk.Combobox(form_frame, state="normal")
    category_combo.insert(0, "General")
    category_combo.grid(row=4, column=1, columnspan=3, sticky="ew", padx=PAD_SM, pady=PAD_XS)

    _form_label(5, tr("common.description", "Описание:"))
    description_entry = ttk.Entry(form_frame)
    description_entry.grid(row=5, column=1, columnspan=3, sticky="ew", padx=PAD_SM, pady=PAD_XS)

    _form_label(6, tr("common.tags", "Теги:"))
    tags_combo = ttk.Combobox(form_frame, state="normal")
    tags_combo.grid(row=6, column=1, columnspan=2, sticky="ew", padx=PAD_SM, pady=PAD_XS)
    Tooltip(
        tags_combo,
        tr(
            "operations.tags.input_tooltip",
            "Введите до 3 тегов через запятую."
            "\nСписок подсказок предлагает существующие теги,"
            "\nновый тег можно дописать вручную."
            "\nТеги приводятся к нижнему регистру,"
            "\nпробелы и спецсимволы удаляются.",
        ),
    )
    selected_tag_color = {"value": TAG_COLOR_PALETTE[0]}
    tag_color_button = tk.Button(
        form_frame,
        width=3,
        height=1,
        relief="raised",
        bd=1,
        overrelief="sunken",
        bg=selected_tag_color["value"],
        activebackground=selected_tag_color["value"],
        highlightthickness=1,
        highlightbackground=palette.border_soft,
        cursor="hand2",
        takefocus=True,
    )
    tag_color_button.grid(
        row=6, column=3, sticky="e", padx=(0, PAD_SM), pady=PAD_XS, ipadx=4, ipady=4
    )
    Tooltip(
        tag_color_button,
        tr(
            "operations.tags.color_tooltip",
            "Цвет тега. Щелкните по квадрату, чтобы открыть палитру.",
        ),
    )

    color_popup_state: dict[str, Any] = {"menu": None}

    _form_label(7, tr("common.wallet", "Кошелек:"))
    operation_wallet_var = tk.StringVar(value="")
    operation_wallet_menu = ttk.Combobox(
        form_frame,
        textvariable=operation_wallet_var,
        values=[],
        state="readonly",
    )
    operation_wallet_menu.grid(row=7, column=1, columnspan=3, sticky="ew", padx=PAD_SM, pady=PAD_XS)
    operation_wallet_map: dict[str, int] = {}

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
        _committed_tags, active_fragment = split_tag_input(raw_tags)
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
            active_tag_name = normalize_tag_name(active_fragment)
            if not active_tag_name and tags:
                active_tag_name = tags[-1]
            if active_tag_name and active_tag_name in tags:
                context.controller.set_tag_color(active_tag_name, selected_tag_color["value"])
            for tag_name in tags:
                if tag_name != active_tag_name and not existing_tags.get(tag_name):
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

    def _bind_focus_navigation(
        widgets: list[tk.Misc],
        *,
        submit_action: Callable[[], None] | None = None,
    ) -> None:
        def _focus_relative(index: int) -> str:
            widgets[index % len(widgets)].focus_set()
            return "break"

        for index, widget in enumerate(widgets):
            widget.bind("<Up>", lambda _event, i=index - 1: _focus_relative(i), add="+")
            widget.bind("<Down>", lambda _event, i=index + 1: _focus_relative(i), add="+")
            if isinstance(widget, ttk.Button):
                widget.bind("<Left>", lambda _event, i=index - 1: _focus_relative(i), add="+")
                widget.bind("<Right>", lambda _event, i=index + 1: _focus_relative(i), add="+")
                widget.bind(
                    "<Return>", lambda _event: (_event.widget.invoke(), "break")[1], add="+"
                )
                widget.bind(
                    "<KP_Enter>", lambda _event: (_event.widget.invoke(), "break")[1], add="+"
                )
            elif callable(submit_action):
                widget.bind("<Return>", lambda _event: (submit_action(), "break")[1], add="+")
                widget.bind("<KP_Enter>", lambda _event: (submit_action(), "break")[1], add="+")

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
    _bind_focus_navigation([*creator_widgets, save_button], submit_action=save_record)

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
