from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass
from tkinter import ttk
from typing import Any, Protocol

from gui.tabs.settings_mandatory_section import build_mandatory_section
from gui.tabs.settings_sections import refresh_wallet_related_ui
from gui.ui_dialogs import messagebox_compat as messagebox
from gui.ui_theme import PAD_LG, PAD_XL


class MandatoryTabContext(Protocol):
    controller: Any
    refresh_operation_wallet_menu: Callable[[], None] | None
    refresh_transfer_wallet_menus: Callable[[], None] | None
    refresh_wallets: Callable[[], None] | None
    refresh_mandatory: Callable[[], None] | None

    def _refresh_list(self) -> None: ...

    def _refresh_charts(self) -> None: ...

    def _refresh_budgets(self) -> None: ...

    def _refresh_all(self) -> None: ...

    def _run_background(
        self,
        task: Callable[[], Any],
        *,
        on_success: Callable[[Any], None],
        on_error: Callable[[BaseException], None] | None = None,
        busy_message: str = "Выполняется операция...",
    ) -> None: ...


@dataclass(slots=True)
class MandatoryTabBindings:
    refresh: Callable[[], None]


def build_mandatory_tab(
    parent: tk.Frame | ttk.Frame,
    context: MandatoryTabContext,
    import_formats: dict[str, dict[str, str]],
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

    refresh_mandatory = build_mandatory_section(
        content,
        context=context,
        import_formats=import_formats,
        refresh_wallets=refresh_wallets,
        base_currency_code=_base_currency_code(),
        messagebox_module=messagebox,
        row_index=0,
    )
    context.refresh_mandatory = refresh_mandatory
    refresh_mandatory()
    return MandatoryTabBindings(refresh=refresh_mandatory)
