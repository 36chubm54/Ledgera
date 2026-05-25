"""Mandatory tab builder."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from gui.ui_theme import PAD_LG, PAD_XL

from ...settings.support.wallets_support import refresh_wallet_related_ui
from .contracts import MandatoryTabBindings, MandatoryTabContext
from ..support.section import build_mandatory_section


def build_mandatory_tab(
    parent: tk.Frame | ttk.Frame,
    context: MandatoryTabContext,
    import_formats: dict[str, dict[str, str]],
    *,
    messagebox_module,
) -> MandatoryTabBindings:
    def _base_currency_code() -> str:
        getter = getattr(context.controller, "get_base_currency_code", None)
        if callable(getter):
            return str(getter() or "").strip().upper() or "KZT"
        return "KZT"

    parent.grid_columnconfigure(0, weight=1)
    parent.grid_rowconfigure(0, weight=1)

    content = ttk.Frame(parent)
    content.grid(row=0, column=0, sticky="nsew", padx=PAD_XL, pady=PAD_LG)
    content.grid_columnconfigure(0, weight=1)
    content.grid_rowconfigure(0, weight=1)

    def refresh_wallets() -> None:
        if context.refresh_wallets is not None:
            context.refresh_wallets()
        else:
            refresh_wallet_related_ui(context)

    mandatory = build_mandatory_section(
        content,
        context=context,
        import_formats=import_formats,
        refresh_wallets=refresh_wallets,
        base_currency_code=_base_currency_code(),
        messagebox_module=messagebox_module,
        row_index=0,
    )
    refresh_mandatory = mandatory.refresh
    context.refresh_mandatory = refresh_mandatory
    refresh_mandatory()
    return MandatoryTabBindings(
        refresh=refresh_mandatory,
        add_mandatory=mandatory.add_mandatory,
        edit_mandatory=mandatory.edit_mandatory,
        add_to_records=mandatory.add_to_records,
        delete_mandatory=mandatory.delete_mandatory,
    )
