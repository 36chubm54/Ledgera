from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass
from tkinter import ttk
from typing import Any

from gui.i18n import tr
from gui.ui_dialogs import messagebox_compat as messagebox
from gui.ui_theme import PAD_LG, PAD_SM, PAD_XS, create_card_section

from .support.wallets_support import (
    MessageBoxLike,
    create_wallet_action,
    delete_wallet_action,
    refresh_wallet_tree,
)
from .support.wallets_ui import (
    bind_wallet_scrolling,
    build_wallet_actions,
    build_wallet_tree,
    create_wallet_form,
)


@dataclass(slots=True)
class WalletsSectionBindings:
    refresh_wallets: Callable[[], None]


def build_wallets_section(
    parent_panel: tk.Frame | ttk.Frame,
    *,
    context: Any,
    base_currency_code: str,
    messagebox_module: MessageBoxLike = messagebox,
    use_card: bool = True,
    row_index: int = 0,
    on_close: Callable[[], None] | None = None,
) -> WalletsSectionBindings:
    pad_x = PAD_SM
    pad_y = PAD_XS

    if use_card:
        wallets_card = create_card_section(parent_panel, tr("settings.wallets", "Кошельки"))
        wallets_card.grid(row=row_index, column=0, sticky="nsew", pady=(0, PAD_LG))
        wallets_frame = wallets_card.winfo_children()[-1]
    else:
        wallets_frame = ttk.Frame(parent_panel)
        wallets_frame.grid(row=row_index, column=0, sticky="nsew")
    wallets_frame.grid_columnconfigure(0, weight=1)
    wallets_frame.grid_rowconfigure(1, weight=1)
    form_fields = create_wallet_form(
        wallets_frame,
        base_currency_code=base_currency_code,
        pad_x=pad_x,
        pad_y=pad_y,
        label_style="FormField.TLabel" if use_card else "TLabel",
        checkbutton_style="FormField.TCheckbutton" if use_card else "TCheckbutton",
    )
    wallet_tree, wallet_scroll, wallet_xscroll = build_wallet_tree(wallets_frame, pad_x=pad_x)
    bind_wallet_scrolling(wallet_tree, wallet_scroll, wallet_xscroll)

    def refresh_wallets() -> None:
        refresh_wallet_tree(wallet_tree, context)

    context.refresh_wallets = refresh_wallets

    def create_wallet() -> None:
        create_wallet_action(
            context=context,
            form_fields=form_fields,
            base_currency_code=base_currency_code,
            messagebox_module=messagebox_module,
            refresh_wallets=refresh_wallets,
        )

    ttk.Button(
        form_fields.name_entry.master,
        text=tr("settings.wallets.create", "Создать кошелек"),
        style="Primary.TButton",
        command=create_wallet,
    ).grid(row=4, column=0, columnspan=2, sticky="ew", pady=(6, 0))

    def delete_wallet() -> None:
        delete_wallet_action(
            wallet_tree=wallet_tree,
            context=context,
            messagebox_module=messagebox_module,
            refresh_wallets=refresh_wallets,
        )

    build_wallet_actions(
        wallets_frame,
        pad_x=pad_x,
        pad_y=pad_y,
        on_delete=delete_wallet,
        on_refresh=refresh_wallets,
        on_close=on_close,
    )

    return WalletsSectionBindings(refresh_wallets=refresh_wallets)
