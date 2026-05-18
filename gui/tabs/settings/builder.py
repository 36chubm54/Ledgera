"""Settings tab builder."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk

from gui.i18n import tr
from gui.ui_theme import PAD_LG, PAD_SM, PAD_XL, create_card_section

from .backup_section import build_backup_section
from .contracts import SettingsTabBindings, SettingsTabContext
from .currency_section import build_audit_section, build_currency_section
from .update_section import build_update_section
from .wallets_section import refresh_wallet_related_ui


def build_settings_tab(
    parent: tk.Frame | ttk.Frame,
    context: SettingsTabContext,
    *,
    messagebox_module,
    wallet_manager_dialog: Callable[..., None],
) -> SettingsTabBindings:
    def _base_currency_code() -> str:
        getter = getattr(context.controller, "get_base_currency_code", None)
        if callable(getter):
            return str(getter() or "").strip().upper() or "KZT"
        return "KZT"

    parent.grid_columnconfigure(0, weight=1)
    parent.grid_rowconfigure(0, weight=1)

    root_panel = ttk.Frame(parent)
    root_panel.grid(row=0, column=0, sticky="nsew", padx=PAD_XL, pady=PAD_LG)
    root_panel.grid_columnconfigure(0, weight=1)
    root_panel.grid_rowconfigure(1, weight=1)

    top_panel = ttk.Frame(root_panel)
    top_panel.grid(row=0, column=0, sticky="ew")
    top_panel.grid_columnconfigure(0, weight=1)

    content_panel = ttk.Frame(root_panel)
    content_panel.grid(row=1, column=0, sticky="nsew", pady=(0, PAD_LG))
    content_panel.grid_columnconfigure(0, weight=3)
    content_panel.grid_columnconfigure(1, weight=2)
    content_panel.grid_rowconfigure(0, weight=1)

    left_panel = ttk.Frame(content_panel)
    left_panel.grid(row=0, column=0, sticky="nsew", padx=(0, PAD_LG))
    left_panel.grid_columnconfigure(0, weight=1)

    right_panel = ttk.Frame(content_panel)
    right_panel.grid(row=0, column=1, sticky="nsew")
    right_panel.grid_columnconfigure(0, weight=1)

    base_currency_code = _base_currency_code()

    def refresh_wallets() -> None:
        refresh_wallet_related_ui(context)

    context.refresh_wallets = refresh_wallets

    wallets_card = create_card_section(top_panel, tr("settings.wallets", "Кошельки"))
    wallets_card.grid(row=0, column=0, sticky="ew", pady=(0, PAD_LG))
    wallets_frame = wallets_card.winfo_children()[-1]
    wallets_frame.grid_columnconfigure(0, weight=1)

    ttk.Label(
        wallets_frame,
        text=tr(
            "settings.wallets.manager_hint",
            "Управление кошельками открывается в отдельном окне.",
        ),
        justify="left",
        style="CardText.TLabel",
    ).grid(row=0, column=0, sticky="w", pady=(0, PAD_SM))

    ttk.Button(
        wallets_frame,
        text=tr("settings.wallets.manage_button", "Управление кошельками..."),
        style="Primary.TButton",
        command=lambda: wallet_manager_dialog(
            parent,
            context=context,
            base_currency_code=base_currency_code,
            messagebox_module=messagebox_module,
        ),
    ).grid(row=1, column=0, sticky="ew")

    build_currency_section(
        left_panel,
        context=context,
        messagebox_module=messagebox_module,
        row_index=1,
    )
    build_backup_section(
        right_panel,
        parent=parent,
        context=context,
        refresh_wallets=refresh_wallets,
        messagebox_module=messagebox_module,
        row_index=1,
    )
    build_update_section(
        right_panel,
        context=context,
        messagebox_module=messagebox_module,
        row_index=0,
    )
    build_audit_section(
        right_panel,
        parent=parent,
        context=context,
        messagebox_module=messagebox_module,
        row_index=2,
    )

    return SettingsTabBindings(refresh=lambda: None)
