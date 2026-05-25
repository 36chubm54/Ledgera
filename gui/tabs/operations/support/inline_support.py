from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from datetime import date
from tkinter import ttk
from typing import Any

from gui.combobox_compat import enable_wayland_combobox_support
from gui.i18n import tr
from gui.tooltip import Tooltip


def date_text(value: object) -> str:
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def create_inline_panel(
    *,
    list_frame: ttk.Frame,
    row: int,
) -> ttk.Frame:
    panel = ttk.Frame(list_frame, style="InlinePanel.TFrame", padding=(8, 6))
    panel.grid(row=row, column=0, columnspan=2, padx=6, sticky="ew")
    panel.grid_columnconfigure(1, weight=1)
    return panel


def build_transfer_editor_widgets(
    *,
    edit_panel: ttk.Frame,
    transfer: Any,
    base_currency_code: Callable[[], str],
    amount_edit_label_text: Callable[[object], str],
    amount_edit_tooltip_text: str,
) -> dict[str, Any]:
    ttk.Label(edit_panel, text=tr("common.date", "Дата:"), style="InlineField.TLabel").grid(
        row=0, column=0, sticky="w"
    )
    date_edit_entry = ttk.Entry(edit_panel)
    date_edit_entry.grid(row=0, column=1, sticky="ew")
    amount_edit_label = ttk.Label(
        edit_panel,
        text=amount_edit_label_text(getattr(transfer, "currency", base_currency_code())),
        style="InlineField.TLabel",
    )
    amount_edit_label.grid(row=1, column=0, sticky="w")
    amount_base_edit_entry = ttk.Entry(edit_panel)
    amount_base_edit_entry.grid(row=1, column=1, sticky="ew")
    Tooltip(amount_edit_label, amount_edit_tooltip_text)
    Tooltip(amount_base_edit_entry, amount_edit_tooltip_text)
    ttk.Label(
        edit_panel,
        text=tr("operations.transfer.from", "Из кошелька:"),
        style="InlineField.TLabel",
    ).grid(row=2, column=0, sticky="w")
    from_wallet_var = tk.StringVar(value="")
    from_wallet_menu = ttk.Combobox(
        edit_panel,
        textvariable=from_wallet_var,
        values=[],
        state="readonly",
    )
    from_wallet_menu.grid(row=2, column=1, sticky="ew")
    enable_wayland_combobox_support(from_wallet_menu, bind_down=False)
    ttk.Label(
        edit_panel,
        text=tr("operations.transfer.to", "В кошелек:"),
        style="InlineField.TLabel",
    ).grid(row=3, column=0, sticky="w")
    to_wallet_var = tk.StringVar(value="")
    to_wallet_menu = ttk.Combobox(
        edit_panel,
        textvariable=to_wallet_var,
        values=[],
        state="readonly",
    )
    to_wallet_menu.grid(row=3, column=1, sticky="ew")
    enable_wayland_combobox_support(to_wallet_menu, bind_down=False)
    ttk.Label(
        edit_panel,
        text=tr("operations.transfer.description", "Описание:"),
        style="InlineField.TLabel",
    ).grid(row=4, column=0, sticky="w")
    description_edit_entry = ttk.Entry(edit_panel)
    description_edit_entry.grid(row=4, column=1, sticky="ew")
    return {
        "date_edit_entry": date_edit_entry,
        "amount_base_edit_entry": amount_base_edit_entry,
        "from_wallet_var": from_wallet_var,
        "from_wallet_menu": from_wallet_menu,
        "to_wallet_var": to_wallet_var,
        "to_wallet_menu": to_wallet_menu,
        "description_edit_entry": description_edit_entry,
    }


def build_record_editor_widgets(
    *,
    edit_panel: ttk.Frame,
    record: Any,
    base_currency_code: Callable[[], str],
    amount_edit_label_text: Callable[[object], str],
    amount_edit_tooltip_text: str,
) -> dict[str, Any]:
    amount_edit_label = ttk.Label(
        edit_panel,
        text=amount_edit_label_text(getattr(record, "currency", base_currency_code())),
        style="InlineField.TLabel",
    )
    amount_edit_label.grid(row=0, column=0, sticky="w")
    amount_entry = ttk.Entry(edit_panel)
    amount_entry.grid(row=0, column=1, sticky="ew")
    Tooltip(amount_edit_label, amount_edit_tooltip_text)
    Tooltip(amount_entry, amount_edit_tooltip_text)
    ttk.Label(edit_panel, text=tr("common.date", "Дата:"), style="InlineField.TLabel").grid(
        row=1, column=0, sticky="w"
    )
    date_edit_entry = ttk.Entry(edit_panel)
    date_edit_entry.grid(row=1, column=1, sticky="ew")
    ttk.Label(edit_panel, text=tr("common.wallet", "Кошелек:"), style="InlineField.TLabel").grid(
        row=2, column=0, sticky="w"
    )
    wallet_edit_var = tk.StringVar(value="")
    wallet_edit_menu = ttk.Combobox(
        edit_panel, textvariable=wallet_edit_var, values=[], state="readonly"
    )
    wallet_edit_menu.grid(row=2, column=1, sticky="ew")
    enable_wayland_combobox_support(wallet_edit_menu, bind_down=False)
    ttk.Label(
        edit_panel, text=tr("common.category", "Категория:"), style="InlineField.TLabel"
    ).grid(row=3, column=0, sticky="w")
    category_edit_combo = ttk.Combobox(edit_panel, state="normal")
    category_edit_combo.grid(row=3, column=1, sticky="ew")
    enable_wayland_combobox_support(category_edit_combo, bind_down=False)
    ttk.Label(
        edit_panel, text=tr("common.description", "Описание:"), style="InlineField.TLabel"
    ).grid(row=4, column=0, sticky="w")
    description_edit_entry = ttk.Entry(edit_panel)
    description_edit_entry.grid(row=4, column=1, sticky="ew")
    ttk.Label(edit_panel, text=tr("common.tags", "Теги:"), style="InlineField.TLabel").grid(
        row=5, column=0, sticky="w"
    )
    tags_edit_combo = ttk.Combobox(edit_panel, state="normal")
    tags_edit_combo.grid(row=5, column=1, sticky="ew")
    return {
        "amount_entry": amount_entry,
        "date_edit_entry": date_edit_entry,
        "wallet_edit_var": wallet_edit_var,
        "wallet_edit_menu": wallet_edit_menu,
        "category_edit_combo": category_edit_combo,
        "description_edit_entry": description_edit_entry,
        "tags_edit_combo": tags_edit_combo,
    }


def build_inline_action_buttons(
    *,
    edit_panel: ttk.Frame,
    row: int,
    on_save: Callable[[], None],
    on_cancel: Callable[[], None],
) -> tuple[ttk.Button, ttk.Button]:
    edit_buttons = ttk.Frame(edit_panel, style="InlinePanel.TFrame")
    edit_buttons.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(8, 0))
    edit_buttons.grid_columnconfigure(0, weight=1)
    edit_buttons.grid_columnconfigure(1, weight=1)
    save_button = ttk.Button(
        edit_buttons,
        text=tr("common.save", "Сохранить"),
        command=on_save,
        style="Primary.TButton",
    )
    save_button.grid(row=0, column=0, sticky="ew", padx=(0, 4))
    cancel_button = ttk.Button(edit_buttons, text=tr("common.cancel", "Отмена"), command=on_cancel)
    cancel_button.grid(row=0, column=1, sticky="ew", padx=(4, 0))
    return save_button, cancel_button


def bind_inline_editor_navigation(
    widgets: list[tk.Misc],
    *,
    on_save: Callable[[], None],
    on_cancel: Callable[[], None],
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
        else:
            widget.bind("<Return>", lambda _event: (on_save(), "break")[1], add="+")
            widget.bind("<KP_Enter>", lambda _event: (on_save(), "break")[1], add="+")
        widget.bind("<Escape>", lambda _event: (on_cancel(), "break")[1], add="+")
