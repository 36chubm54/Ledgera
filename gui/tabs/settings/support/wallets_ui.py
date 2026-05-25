from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk

from gui.i18n import tr
from gui.ui_helpers import attach_treeview_scrollbars, enable_treeview_column_autosize
from gui.ui_theme import enable_treeview_zebra

from .wallets_support import WalletFormFields


def create_wallet_form(
    parent: tk.Misc,
    *,
    base_currency_code: str,
    pad_x: int,
    pad_y: int,
    label_style: str = "TLabel",
    checkbutton_style: str = "TCheckbutton",
) -> WalletFormFields:
    form = ttk.Frame(parent)
    form.grid(row=0, column=0, sticky="ew", padx=pad_x, pady=pad_y)
    form.grid_columnconfigure(1, weight=1)

    ttk.Label(
        form,
        text=tr("settings.wallets.name", "Название:"),
        style=label_style,
    ).grid(row=0, column=0, sticky="w")
    wallet_name_entry = ttk.Entry(form)
    wallet_name_entry.grid(row=0, column=1, sticky="ew", pady=2)

    ttk.Label(
        form,
        text=tr("settings.wallets.currency", "Валюта:"),
        style=label_style,
    ).grid(row=1, column=0, sticky="w")
    wallet_currency_entry = ttk.Entry(form, width=8)
    wallet_currency_entry.insert(0, base_currency_code)
    wallet_currency_entry.grid(row=1, column=1, sticky="ew", pady=2)

    ttk.Label(
        form,
        text=tr("settings.wallets.initial_balance", "Начальный баланс:"),
        style=label_style,
    ).grid(row=2, column=0, sticky="w")
    wallet_initial_entry = ttk.Entry(form)
    wallet_initial_entry.insert(0, "0")
    wallet_initial_entry.grid(row=2, column=1, sticky="ew", pady=2)

    wallet_allow_negative_var = tk.BooleanVar(value=False)
    ttk.Checkbutton(
        form,
        text=tr("settings.wallets.allow_negative", "Разрешить отрицательный баланс"),
        variable=wallet_allow_negative_var,
        style=checkbutton_style,
    ).grid(
        row=3,
        column=0,
        columnspan=2,
        sticky="w",
        pady=2,
    )
    return WalletFormFields(
        name_entry=wallet_name_entry,
        currency_entry=wallet_currency_entry,
        initial_entry=wallet_initial_entry,
        allow_negative_var=wallet_allow_negative_var,
    )


def build_wallet_tree(
    parent: tk.Misc,
    *,
    pad_x: int,
) -> tuple[ttk.Treeview, ttk.Scrollbar | None, ttk.Scrollbar | None]:
    list_frame = ttk.Frame(parent)
    list_frame.grid(row=1, column=0, sticky="nsew", padx=pad_x)
    list_frame.grid_rowconfigure(0, weight=1)
    list_frame.grid_columnconfigure(0, weight=1)

    wallet_columns = (
        "id",
        "name",
        "currency",
        "initial_balance",
        "balance",
        "allow_negative",
        "active",
    )
    wallet_tree = ttk.Treeview(
        list_frame,
        columns=wallet_columns,
        show="headings",
        selectmode="browse",
        height=8,
    )
    enable_treeview_zebra(wallet_tree)
    for col, text, width, minwidth, stretch, anchor in (
        ("id", "ID", 40, 40, False, "e"),
        ("name", tr("settings.wallets.name_short", "Название"), 100, 100, True, "w"),
        ("currency", tr("settings.wallets.currency_short", "Вал."), 60, 60, False, "center"),
        (
            "initial_balance",
            tr("settings.wallets.initial_balance_short", "Старт"),
            110,
            90,
            False,
            "e",
        ),
        ("balance", tr("settings.wallets.balance", "Баланс"), 110, 90, False, "e"),
        (
            "allow_negative",
            tr("settings.wallets.allow_negative_short", "Минус"),
            92,
            92,
            False,
            "center",
        ),
        ("active", tr("settings.wallets.active", "Активен"), 90, 90, False, "center"),
    ):
        wallet_tree.heading(col, text=text)
        wallet_tree.column(col, width=width, minwidth=minwidth, stretch=stretch, anchor=anchor)  # type: ignore[arg-type]
    enable_treeview_column_autosize(wallet_tree, columns=("name",), max_width=320)
    wallet_tree.grid(row=0, column=0, sticky="nsew")
    wallet_scroll, wallet_xscroll = attach_treeview_scrollbars(
        list_frame, wallet_tree, row=0, column=0, horizontal=True
    )
    return wallet_tree, wallet_scroll, wallet_xscroll


def bind_wallet_scrolling(
    wallet_tree: ttk.Treeview,
    wallet_scroll: ttk.Scrollbar | None,
    wallet_xscroll: ttk.Scrollbar | None,
) -> None:
    def _wallet_scroll_units(delta: int, *, multiplier: int = 12) -> int:
        if delta == 0:
            return 0
        base_units = max(1, abs(int(delta)) // 120)
        return base_units * multiplier

    def _scroll_wallet_vertically(direction: int, units: int) -> str:
        wallet_tree.yview_scroll(direction * units, "units")
        return "break"

    def _scroll_wallet_horizontally(direction: int, units: int) -> str:
        wallet_tree.xview_scroll(direction * units, "units")
        return "break"

    def _on_wallet_mousewheel(event: tk.Event) -> str:
        delta = int(getattr(event, "delta", 0))
        units = _wallet_scroll_units(delta, multiplier=8)
        if units <= 0:
            return "break"
        direction = -1 if delta > 0 else 1
        return _scroll_wallet_vertically(direction, units)

    def _on_wallet_shift_mousewheel(event: tk.Event) -> str:
        delta = int(getattr(event, "delta", 0))
        units = _wallet_scroll_units(delta, multiplier=12)
        if units <= 0:
            return "break"
        direction = -1 if delta > 0 else 1
        return _scroll_wallet_horizontally(direction, units)

    def _on_wallet_button4(_event: tk.Event) -> str:
        return _scroll_wallet_vertically(-1, 3)

    def _on_wallet_button5(_event: tk.Event) -> str:
        return _scroll_wallet_vertically(1, 3)

    def _on_wallet_shift_button4(_event: tk.Event) -> str:
        return _scroll_wallet_horizontally(-1, 3)

    def _on_wallet_shift_button5(_event: tk.Event) -> str:
        return _scroll_wallet_horizontally(1, 3)

    for widget in (wallet_tree, wallet_scroll, wallet_xscroll):
        if widget is not None:
            widget.bind("<MouseWheel>", _on_wallet_mousewheel, add="+")
            widget.bind("<Shift-MouseWheel>", _on_wallet_shift_mousewheel, add="+")
            widget.bind("<Button-4>", _on_wallet_button4, add="+")
            widget.bind("<Button-5>", _on_wallet_button5, add="+")
            widget.bind("<Shift-Button-4>", _on_wallet_shift_button4, add="+")
            widget.bind("<Shift-Button-5>", _on_wallet_shift_button5, add="+")


def build_wallet_actions(
    parent: tk.Misc,
    *,
    pad_x: int,
    pad_y: int,
    on_delete: Callable[[], None],
    on_refresh: Callable[[], None],
    on_close: Callable[[], None] | None,
) -> None:
    wallet_actions = ttk.Frame(parent)
    wallet_actions.grid(row=2, column=0, sticky="ew", padx=pad_x, pady=pad_y)
    wallet_actions.grid_columnconfigure(0, weight=1)
    wallet_actions.grid_columnconfigure(1, weight=1)
    if on_close is not None:
        wallet_actions.grid_columnconfigure(2, weight=1)

    ttk.Button(
        wallet_actions,
        text=tr("settings.wallets.delete", "Удалить кошелек"),
        command=on_delete,
    ).grid(row=0, column=0, sticky="ew", padx=(0, 4))
    ttk.Button(
        wallet_actions,
        text=tr("common.refresh", "Обновить"),
        command=on_refresh,
    ).grid(row=0, column=1, sticky="ew", padx=(4, 0))
    if on_close is not None:
        ttk.Button(
            wallet_actions,
            text=tr("common.close", "Закрыть"),
            command=on_close,
        ).grid(row=0, column=2, sticky="ew", padx=(8, 0))
