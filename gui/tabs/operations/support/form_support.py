from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from datetime import date
from tkinter import ttk
from typing import Any

from gui.i18n import tr
from gui.tooltip import Tooltip
from gui.ui_theme import PAD_SM, PAD_XS, get_palette
from utils.records.tags import TAG_COLOR_PALETTE, normalize_tag_name


def create_form_label_builder(
    form_frame: tk.Misc, *, label_width: int
) -> Callable[[int, str], ttk.Label]:
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

    return _form_label


def build_basic_form_fields(
    *,
    form_frame: tk.Misc,
    form_label: Callable[[int, str], ttk.Label],
    enable_combobox_support: Callable[..., Any],
    income_label: str,
    base_currency_code: str,
) -> dict[str, Any]:
    form_label(0, tr("common.type", "Тип:"))
    type_options = [income_label, tr("operations.type.expense", "Расход")]
    type_combo = ttk.Combobox(form_frame, values=type_options, state="readonly")
    type_combo.set(income_label)
    type_combo.grid(row=0, column=1, columnspan=3, sticky="ew", padx=PAD_SM, pady=PAD_XS)
    enable_combobox_support(type_combo, bind_down=False)

    form_label(1, tr("common.date", "Дата:"))
    date_entry = ttk.Entry(form_frame)
    date_entry.grid(row=1, column=1, columnspan=3, sticky="ew", padx=PAD_SM, pady=PAD_XS)
    date_entry.insert(0, date.today().isoformat())

    form_label(2, tr("common.amount", "Сумма:"))
    amount_entry = ttk.Entry(form_frame)
    amount_entry.grid(row=2, column=1, columnspan=3, sticky="ew", padx=PAD_SM, pady=PAD_XS)

    form_label(3, tr("common.currency", "Валюта:"))
    currency_entry = ttk.Entry(form_frame)
    currency_entry.insert(0, base_currency_code)
    currency_entry.grid(row=3, column=1, columnspan=3, sticky="ew", padx=PAD_SM, pady=PAD_XS)

    form_label(4, tr("common.category", "Категория:"))
    category_combo = ttk.Combobox(form_frame, state="normal")
    category_combo.insert(0, "General")
    category_combo.grid(row=4, column=1, columnspan=3, sticky="ew", padx=PAD_SM, pady=PAD_XS)
    enable_combobox_support(category_combo, bind_down=False)

    form_label(5, tr("common.description", "Описание:"))
    description_entry = ttk.Entry(form_frame)
    description_entry.grid(row=5, column=1, columnspan=3, sticky="ew", padx=PAD_SM, pady=PAD_XS)

    return {
        "type_combo": type_combo,
        "date_entry": date_entry,
        "amount_entry": amount_entry,
        "currency_entry": currency_entry,
        "category_combo": category_combo,
        "description_entry": description_entry,
    }


def build_tag_widgets(
    *,
    form_frame: tk.Misc,
    form_label: Callable[[int, str], ttk.Label],
) -> tuple[ttk.Combobox, tk.Button, dict[str, str], dict[str, Any], Any]:
    form_label(6, tr("common.tags", "Теги:"))
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
    palette = get_palette()
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
    return tags_combo, tag_color_button, selected_tag_color, color_popup_state, palette


def build_wallet_widgets(
    *,
    form_frame: tk.Misc,
    form_label: Callable[[int, str], ttk.Label],
    enable_combobox_support: Callable[..., Any],
) -> tuple[tk.StringVar, ttk.Combobox, dict[str, int]]:
    form_label(7, tr("common.wallet", "Кошелек:"))
    operation_wallet_var = tk.StringVar(value="")
    operation_wallet_menu = ttk.Combobox(
        form_frame,
        textvariable=operation_wallet_var,
        values=[],
        state="readonly",
    )
    operation_wallet_menu.grid(row=7, column=1, columnspan=3, sticky="ew", padx=PAD_SM, pady=PAD_XS)
    enable_combobox_support(operation_wallet_menu, bind_down=False)
    operation_wallet_map: dict[str, int] = {}
    return operation_wallet_var, operation_wallet_menu, operation_wallet_map


def bind_focus_navigation(
    widgets: list[tk.Misc],
    *,
    submit_action: Callable[[], None] | None = None,
) -> None:
    def _focus_relative(index: int) -> str:
        widgets[index % len(widgets)].focus_set()
        return "break"

    for index, widget in enumerate(widgets):
        if not isinstance(widget, ttk.Combobox):
            widget.bind("<Up>", lambda _event, i=index - 1: _focus_relative(i), add="+")
            widget.bind("<Down>", lambda _event, i=index + 1: _focus_relative(i), add="+")
        if isinstance(widget, ttk.Button):
            widget.bind("<Left>", lambda _event, i=index - 1: _focus_relative(i), add="+")
            widget.bind("<Right>", lambda _event, i=index + 1: _focus_relative(i), add="+")
            widget.bind("<Return>", lambda _event: (_event.widget.invoke(), "break")[1], add="+")
            widget.bind("<KP_Enter>", lambda _event: (_event.widget.invoke(), "break")[1], add="+")
        elif callable(submit_action):
            widget.bind("<Return>", lambda _event: (submit_action(), "break")[1], add="+")
            widget.bind("<KP_Enter>", lambda _event: (submit_action(), "break")[1], add="+")


def active_tag_name(raw_input: str, tags: tuple[str, ...]) -> str:
    from ..core.tag_input import split_tag_input

    _committed_tags, active_fragment = split_tag_input(raw_input)
    normalized = normalize_tag_name(active_fragment)
    if normalized:
        return normalized
    if tags:
        return tags[-1]
    return ""
