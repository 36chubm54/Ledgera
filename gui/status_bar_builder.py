from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from tkinter import ttk
from typing import Any, Protocol

from gui.hotkeys import _show_hotkey_help
from gui.i18n import get_available_languages, get_language, tr
from gui.ui_theme import PAD_SM, get_theme
from version import __version__


class StatusBarBuilderController(Protocol):
    def get_available_display_currencies(self) -> list[str]: ...

    def get_display_currency(self) -> str: ...


class StatusBarBuilderOwner(Protocol):
    controller: StatusBarBuilderController

    def _on_online_toggle(self) -> None: ...

    def _on_display_currency_changed(self, _event: tk.Event | None = None) -> None: ...

    def _on_language_changed(self, _event: tk.Event | None = None) -> None: ...

    def _on_theme_changed(self, _event: tk.Event | None = None) -> None: ...


@dataclass(slots=True)
class StatusBarBuildResult:
    frame: ttk.Frame
    online_var: tk.BooleanVar
    currency_status_label: ttk.Label
    price_status_label: ttk.Label
    display_currency_var: tk.StringVar
    display_currency_combo: ttk.Combobox
    language_var: tk.StringVar
    language_combo: ttk.Combobox
    theme_var: tk.StringVar
    theme_combo: ttk.Combobox
    theme_label_to_key: dict[str, str]


def combobox_code_width(options: list[str], *, minimum: int = 4, maximum: int = 6) -> int:
    return max(minimum, min(maximum, max(len(code) for code in options)))


def build_language_codes() -> list[str]:
    language_codes = [code.upper() for code in get_available_languages()] or ["RU"]
    current_language = get_language().upper()
    if current_language not in language_codes:
        language_codes.insert(0, current_language)
    return language_codes


def build_theme_label_to_key() -> dict[str, str]:
    return {
        tr("app.theme.light", "Светлая"): "light",
        tr("app.theme.dark", "Темная"): "dark",
    }


def resolve_current_theme_label(theme_label_to_key: dict[str, str]) -> str:
    theme_labels = list(theme_label_to_key.keys())
    return next(
        (label for label, key in theme_label_to_key.items() if key == get_theme()),
        theme_labels[0],
    )


def build_status_bar(owner: Any) -> StatusBarBuildResult:
    typed_owner = owner
    bar = ttk.Frame(owner, style="StatusBar.TFrame", padding=(PAD_SM, 3))
    bar.grid_columnconfigure(7, weight=1)

    online_var = tk.BooleanVar(value=False)
    online_check = ttk.Checkbutton(
        bar,
        text=tr("app.status.online", "Онлайн"),
        variable=online_var,
        command=typed_owner._on_online_toggle,
        style="StatusBar.TCheckbutton",
    )
    online_check.grid(row=0, column=0, sticky="w", padx=(PAD_SM, PAD_SM), pady=4)

    ttk.Separator(bar, orient=tk.VERTICAL, style="StatusBar.TSeparator").grid(
        row=0, column=1, sticky="ns", pady=5, padx=(0, PAD_SM)
    )
    currency_status_label = ttk.Label(
        bar,
        text=tr("app.status.currency_offline", "Курсы: офлайн"),
        anchor="w",
        style="StatusBar.TLabel",
    )
    currency_status_label.grid(row=0, column=2, sticky="w", padx=(0, PAD_SM), pady=4)

    ttk.Separator(bar, orient=tk.VERTICAL, style="StatusBar.TSeparator").grid(
        row=0, column=3, sticky="ns", pady=5, padx=(0, PAD_SM)
    )
    price_status_label = ttk.Label(
        bar,
        text=tr("app.status.prices_local", "Цены активов: локально"),
        anchor="w",
        style="StatusBar.TLabel",
    )
    price_status_label.grid(row=0, column=4, sticky="w", padx=(0, PAD_SM), pady=4)

    ttk.Separator(bar, orient=tk.VERTICAL, style="StatusBar.TSeparator").grid(
        row=0, column=5, sticky="ns", pady=5, padx=(0, PAD_SM)
    )
    ttk.Label(
        bar,
        text=tr("app.status.display_currency", "Показ:"),
        style="StatusBarMuted.TLabel",
    ).grid(row=0, column=6, sticky="w", padx=(0, 6), pady=4)
    display_values = typed_owner.controller.get_available_display_currencies()
    display_currency_var = tk.StringVar(value=typed_owner.controller.get_display_currency())
    display_currency_combo = ttk.Combobox(
        bar,
        textvariable=display_currency_var,
        values=display_values,
        width=combobox_code_width(display_values),
        state="readonly",
        style="StatusBar.TCombobox",
    )
    display_currency_combo.grid(row=0, column=7, sticky="w", padx=(0, PAD_SM), pady=2)
    display_currency_combo.bind(
        "<<ComboboxSelected>>", typed_owner._on_display_currency_changed, add="+"
    )

    ttk.Separator(bar, orient=tk.VERTICAL, style="StatusBar.TSeparator").grid(
        row=0, column=8, sticky="ns", pady=5, padx=(0, PAD_SM)
    )
    ttk.Label(
        bar,
        text=tr("common.language", "Язык:"),
        style="StatusBarMuted.TLabel",
    ).grid(row=0, column=9, sticky="w", padx=(0, 6), pady=4)
    language_codes = build_language_codes()
    language_var = tk.StringVar(value=get_language().upper())
    language_combo = ttk.Combobox(
        bar,
        textvariable=language_var,
        values=language_codes,
        width=combobox_code_width(language_codes),
        state="readonly",
        style="StatusBar.TCombobox",
    )
    language_combo.grid(row=0, column=10, sticky="w", padx=(0, PAD_SM), pady=2)
    language_combo.bind("<<ComboboxSelected>>", typed_owner._on_language_changed, add="+")

    ttk.Separator(bar, orient=tk.VERTICAL, style="StatusBar.TSeparator").grid(
        row=0, column=11, sticky="ns", pady=5, padx=(0, PAD_SM)
    )
    ttk.Label(
        bar,
        text=tr("common.theme", "Тема:"),
        style="StatusBarMuted.TLabel",
    ).grid(row=0, column=12, sticky="w", padx=(0, 6), pady=4)
    theme_label_to_key = build_theme_label_to_key()
    theme_labels = list(theme_label_to_key.keys())
    theme_var = tk.StringVar(value=resolve_current_theme_label(theme_label_to_key))
    theme_combo = ttk.Combobox(
        bar,
        textvariable=theme_var,
        values=theme_labels,
        width=max(10, max(len(label) for label in theme_labels)),
        state="readonly",
        style="StatusBar.TCombobox",
    )
    theme_combo.grid(row=0, column=13, sticky="w", padx=(0, PAD_SM), pady=2)
    theme_combo.bind("<<ComboboxSelected>>", typed_owner._on_theme_changed, add="+")

    ttk.Separator(bar, orient=tk.VERTICAL, style="StatusBar.TSeparator").grid(
        row=0, column=14, sticky="ns", pady=5, padx=(0, PAD_SM)
    )
    ttk.Label(
        bar,
        text=tr("app.status.version", "v{version}", version=__version__),
        style="StatusBarMuted.TLabel",
    ).grid(row=0, column=15, sticky="e", padx=(0, PAD_SM), pady=4)
    ttk.Separator(bar, orient=tk.VERTICAL, style="StatusBar.TSeparator").grid(
        row=0, column=16, sticky="ns", pady=5, padx=(0, 4)
    )
    ttk.Button(
        bar,
        text=tr("app.status.hotkeys_help", "?"),
        style="StatusBar.TButton",
        command=lambda: _show_hotkey_help(owner),
        takefocus=False,
        width=1,
    ).grid(row=0, column=17, sticky="e", padx=(0, 6), pady=2)

    return StatusBarBuildResult(
        frame=bar,
        online_var=online_var,
        currency_status_label=currency_status_label,
        price_status_label=price_status_label,
        display_currency_var=display_currency_var,
        display_currency_combo=display_currency_combo,
        language_var=language_var,
        language_combo=language_combo,
        theme_var=theme_var,
        theme_combo=theme_combo,
        theme_label_to_key=theme_label_to_key,
    )
