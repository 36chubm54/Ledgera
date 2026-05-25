from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from datetime import date
from tkinter import ttk
from typing import Any

from gui.i18n import tr
from gui.ui_theme import PAD_SM, PAD_XS


def build_transfer_fields(
    *,
    transfer_frame: tk.Misc,
    enable_combobox_support: Callable[..., Any],
    base_currency_code: str,
) -> dict[str, Any]:
    ttk.Label(
        transfer_frame,
        text=tr("operations.transfer.from", "Из кошелька:"),
        style="FormField.TLabel",
    ).grid(row=0, column=0, sticky="w", padx=PAD_SM, pady=PAD_XS)
    transfer_from_var = tk.StringVar(value="")
    transfer_from_menu = ttk.Combobox(
        transfer_frame,
        textvariable=transfer_from_var,
        values=[],
        state="readonly",
    )
    transfer_from_menu.grid(row=0, column=1, sticky="ew", padx=PAD_SM, pady=PAD_XS)
    enable_combobox_support(transfer_from_menu, bind_down=False)

    ttk.Label(
        transfer_frame,
        text=tr("operations.transfer.to", "В кошелек:"),
        style="FormField.TLabel",
    ).grid(row=1, column=0, sticky="w", padx=PAD_SM, pady=PAD_XS)
    transfer_to_var = tk.StringVar(value="")
    transfer_to_menu = ttk.Combobox(
        transfer_frame,
        textvariable=transfer_to_var,
        values=[],
        state="readonly",
    )
    transfer_to_menu.grid(row=1, column=1, sticky="ew", padx=PAD_SM, pady=PAD_XS)
    enable_combobox_support(transfer_to_menu, bind_down=False)

    ttk.Label(
        transfer_frame,
        text=tr("common.date", "Дата:"),
        style="FormField.TLabel",
    ).grid(row=2, column=0, sticky="w", padx=PAD_SM, pady=PAD_XS)
    transfer_date_entry = ttk.Entry(transfer_frame)
    transfer_date_entry.grid(row=2, column=1, sticky="ew", padx=PAD_SM, pady=PAD_XS)
    transfer_date_entry.insert(0, date.today().isoformat())

    ttk.Label(
        transfer_frame,
        text=tr("common.amount", "Сумма:"),
        style="FormField.TLabel",
    ).grid(row=3, column=0, sticky="w", padx=PAD_SM, pady=PAD_XS)
    transfer_amount_entry = ttk.Entry(transfer_frame)
    transfer_amount_entry.grid(row=3, column=1, sticky="ew", padx=PAD_SM, pady=PAD_XS)

    ttk.Label(
        transfer_frame,
        text=tr("common.currency", "Валюта:"),
        style="FormField.TLabel",
    ).grid(row=4, column=0, sticky="w", padx=PAD_SM, pady=PAD_XS)
    transfer_currency_entry = ttk.Entry(transfer_frame)
    transfer_currency_entry.insert(0, base_currency_code)
    transfer_currency_entry.grid(row=4, column=1, sticky="ew", padx=PAD_SM, pady=PAD_XS)

    ttk.Label(
        transfer_frame,
        text=tr("operations.transfer.commission", "Комиссия:"),
        style="FormField.TLabel",
    ).grid(row=5, column=0, sticky="w", padx=PAD_SM, pady=PAD_XS)
    transfer_commission_entry = ttk.Entry(transfer_frame)
    transfer_commission_entry.insert(0, "0")
    transfer_commission_entry.grid(row=5, column=1, sticky="ew", padx=PAD_SM, pady=PAD_XS)

    ttk.Label(
        transfer_frame,
        text=tr("operations.transfer.commission_currency", "Валюта комиссии:"),
        style="FormField.TLabel",
    ).grid(row=6, column=0, sticky="w", padx=PAD_SM, pady=PAD_XS)
    transfer_commission_currency_entry = ttk.Entry(transfer_frame)
    transfer_commission_currency_entry.insert(0, base_currency_code)
    transfer_commission_currency_entry.grid(row=6, column=1, sticky="ew", padx=PAD_SM, pady=PAD_XS)

    ttk.Label(
        transfer_frame,
        text=tr("common.description", "Описание:"),
        style="FormField.TLabel",
    ).grid(row=7, column=0, sticky="w", padx=PAD_SM, pady=PAD_XS)
    transfer_description_entry = ttk.Entry(transfer_frame)
    transfer_description_entry.grid(row=7, column=1, sticky="ew", padx=PAD_SM, pady=PAD_XS)

    return {
        "transfer_from_var": transfer_from_var,
        "transfer_from_menu": transfer_from_menu,
        "transfer_to_var": transfer_to_var,
        "transfer_to_menu": transfer_to_menu,
        "transfer_date_entry": transfer_date_entry,
        "transfer_amount_entry": transfer_amount_entry,
        "transfer_currency_entry": transfer_currency_entry,
        "transfer_commission_entry": transfer_commission_entry,
        "transfer_commission_currency_entry": transfer_commission_currency_entry,
        "transfer_description_entry": transfer_description_entry,
    }


def bind_transfer_focus_navigation(
    widgets: list[tk.Misc],
    *,
    submit_action: Callable[[], None],
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
            widget.bind("<Return>", lambda _event: (_event.widget.invoke(), "break")[1], add="+")
            widget.bind("<KP_Enter>", lambda _event: (_event.widget.invoke(), "break")[1], add="+")
        else:
            widget.bind("<Return>", lambda _event: (submit_action(), "break")[1], add="+")
            widget.bind("<KP_Enter>", lambda _event: (submit_action(), "break")[1], add="+")
