from __future__ import annotations

import logging
import tkinter as tk
from types import SimpleNamespace
from tkinter import ttk
from typing import Any, cast
from unittest.mock import patch

from gui.tabs.mandatory.tree_section import build_mandatory_actions_row
from gui.tabs.operations.journal_section import build_journal_section
from gui.tabs.operations.transfer_section import build_transfer_section


class _DummyOperationsController:
    def load_active_wallets(self) -> list[object]:
        return []


def _find_combos(parent: tk.Misc) -> list[ttk.Combobox]:
    found: list[ttk.Combobox] = []

    def _walk(node: tk.Misc) -> None:
        for child in node.winfo_children():
            if isinstance(child, ttk.Combobox):
                found.append(child)
            _walk(child)

    _walk(parent)
    return found


def test_transfer_section_attaches_linux_popup_support_to_wallet_selectors() -> None:
    root = tk.Tk()
    root.withdraw()
    try:
        parent = ttk.PanedWindow(root, orient=tk.HORIZONTAL)
        parent.pack(fill="both", expand=True)
        context = cast(
            Any,
            SimpleNamespace(
                controller=_DummyOperationsController(),
            ),
        )

        with patch(
            "gui.tabs.operations.transfer_section.enable_wayland_combobox_support",
            wraps=lambda widget, **_kwargs: setattr(widget, "_compat_attached", True),
        ) as wrapped:
            build_transfer_section(
                parent,
                context=context,
                logger=logging.getLogger("test"),
                base_currency_code=lambda: "KZT",
                on_saved=lambda: None,
            )

        assert wrapped.call_count == 2
        combos = _find_combos(parent)
        assert len(combos) >= 2
        assert getattr(combos[0], "_compat_attached", False) is True
        assert getattr(combos[1], "_compat_attached", False) is True
    finally:
        root.destroy()


def test_journal_section_attaches_linux_popup_support_to_import_combos() -> None:
    root = tk.Tk()
    root.withdraw()
    try:
        parent = ttk.Frame(root)
        parent.pack(fill="both", expand=True)

        with patch(
            "gui.tabs.operations.journal_section.enable_wayland_combobox_support",
            wraps=lambda widget, **_kwargs: setattr(widget, "_compat_attached", True),
        ) as wrapped:
            build_journal_section(
                parent,
                format_options=["CSV", "XLSX"],
                on_delete_selected=lambda: None,
                on_edit_selected=lambda: None,
                on_refresh_list=lambda: None,
                on_delete_all=lambda: None,
                on_import=lambda: None,
                on_export=lambda: None,
            )

        assert wrapped.call_count == 2
        combos = _find_combos(parent)
        assert len(combos) == 2
        assert all(getattr(combo, "_compat_attached", False) for combo in combos)
    finally:
        root.destroy()


def test_mandatory_actions_row_attaches_linux_popup_support_to_format_combo() -> None:
    root = tk.Tk()
    root.withdraw()
    try:
        parent = ttk.Frame(root)
        parent.pack(fill="both", expand=True)
        format_var = tk.StringVar(value="CSV")

        with patch(
            "gui.tabs.mandatory.tree_section.enable_wayland_combobox_support",
            wraps=lambda widget, **_kwargs: setattr(widget, "_compat_attached", True),
        ) as wrapped:
            build_mandatory_actions_row(
                parent,
                format_var=format_var,
                on_edit=lambda: None,
                on_add_to_records=lambda: None,
                on_delete=lambda: None,
                on_delete_all=lambda: None,
                on_refresh=lambda: None,
                on_import=lambda: None,
                on_export=lambda: None,
                pad_x=0,
                pad_y=0,
            )

        assert wrapped.call_count == 1
        combos = _find_combos(parent)
        assert len(combos) == 1
        assert getattr(combos[0], "_compat_attached", False) is True
    finally:
        root.destroy()
