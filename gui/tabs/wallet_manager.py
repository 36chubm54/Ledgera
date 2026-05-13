from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk
from typing import Any, Protocol

from gui.i18n import tr
from gui.tabs.settings_sections import MessageBoxLike, build_wallets_section
from gui.ui_dialogs import messagebox_compat as messagebox
from gui.ui_helpers import center_dialog
from gui.ui_theme import PAD_LG


class WalletManagerContext(Protocol):
    controller: Any
    refresh_operation_wallet_menu: Callable[[], None] | None
    refresh_transfer_wallet_menus: Callable[[], None] | None
    refresh_wallets: Callable[[], None] | None


def create_wallet_manager_dialog(
    parent: tk.Misc,
    *,
    context: WalletManagerContext,
    base_currency_code: str,
    messagebox_module: MessageBoxLike = messagebox,
) -> tk.Toplevel:
    dialog = tk.Toplevel(parent)
    dialog.withdraw()
    dialog.title(tr("settings.wallets.dialog_title", "Управление кошельками"))
    dialog.transient(parent.winfo_toplevel())
    dialog.minsize(760, 420)
    dialog.resizable(True, True)
    dialog.grid_columnconfigure(0, weight=1)
    dialog.grid_rowconfigure(0, weight=1)

    container = ttk.Frame(dialog, padding=12)
    container.grid(row=0, column=0, sticky="nsew")
    container.grid_columnconfigure(0, weight=1)
    container.grid_rowconfigure(1, weight=1)

    ttk.Label(
        container,
        text=tr("settings.wallets.dialog_title", "Управление кошельками"),
        font=("Segoe UI", 11, "bold"),
    ).grid(row=0, column=0, sticky="w", pady=(0, PAD_LG))

    previous_refresh_wallets = context.refresh_wallets

    def _close() -> None:
        context.refresh_wallets = previous_refresh_wallets
        dialog.destroy()

    bindings = build_wallets_section(
        container,
        context=context,
        base_currency_code=base_currency_code,
        messagebox_module=messagebox_module,
        use_card=False,
        row_index=1,
        on_close=_close,
    )
    bindings.refresh_wallets()

    dialog.protocol("WM_DELETE_WINDOW", _close)
    dialog.bind("<Escape>", lambda _event: (_close(), "break")[1], add="+")

    center_dialog(dialog, parent, min_width=760, min_height=420)
    dialog.deiconify()
    return dialog


def show_wallet_manager_dialog(
    parent: tk.Misc,
    *,
    context: WalletManagerContext,
    base_currency_code: str,
    messagebox_module: MessageBoxLike = messagebox,
) -> None:
    dialog = create_wallet_manager_dialog(
        parent,
        context=context,
        base_currency_code=base_currency_code,
        messagebox_module=messagebox_module,
    )
    dialog.grab_set()
    parent.wait_window(dialog)
