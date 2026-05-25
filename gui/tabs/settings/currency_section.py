from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any

from gui.combobox_compat import enable_wayland_combobox_support
from gui.i18n import tr
from gui.tooltip import Tooltip
from gui.ui_dialogs import messagebox_compat as messagebox
from gui.ui_theme import PAD_LG, PAD_SM, PAD_XS, create_card_section

from .dialogs.audit import show_audit_report_dialog
from .support.currency_support import (
    build_currency_section_state,
    refresh_provider_choices,
    run_audit_action,
    save_currency_settings,
)
from .support.wallets_support import MessageBoxLike


def build_currency_section(
    parent_panel: tk.Frame | ttk.Frame,
    *,
    context: Any,
    messagebox_module: MessageBoxLike = messagebox,
    row_index: int = 0,
) -> None:
    pad_x = PAD_SM
    pad_y = PAD_XS

    currency_card = create_card_section(
        parent_panel,
        tr("settings.currency.title", "Валюта и курсы"),
    )
    currency_card.grid(row=row_index, column=0, sticky="ew", pady=(0, PAD_LG))
    currency_frame = currency_card.winfo_children()[-1]
    currency_frame.grid_columnconfigure(1, weight=1)

    state = build_currency_section_state(context)
    display_currency_var = tk.StringVar(value=state.display_currency)
    provider_mode_var = tk.StringVar(value=state.provider_mode)
    primary_provider_var = tk.StringVar(value=state.primary_provider)
    fallback_provider_var = tk.StringVar(value=state.fallback_provider)
    exchange_api_key_var = tk.StringVar(value=state.exchange_api_key)
    auto_update_var = tk.BooleanVar(value=state.auto_update)
    update_interval_var = tk.StringVar(value=state.update_interval)

    ttk.Label(
        currency_frame,
        text=tr("settings.currency.base_currency", "Базовая валюта:"),
        style="FormField.TLabel",
    ).grid(row=0, column=0, sticky="w", padx=pad_x, pady=pad_y)
    base_currency_frame = ttk.Frame(currency_frame, style="CardBody.TFrame")
    base_currency_frame.grid(row=0, column=1, sticky="w", padx=(0, pad_x), pady=pad_y)
    ttk.Label(
        base_currency_frame,
        text=state.base_currency_text,
        style="FormField.TLabel",
    ).grid(row=0, column=0, sticky="w")
    base_currency_info = ttk.Label(base_currency_frame, text="ⓘ", style="FormField.TLabel")
    base_currency_info.grid(row=0, column=1, sticky="w", padx=(PAD_XS, 0))
    Tooltip(
        base_currency_info,
        tr(
            "settings.currency.base_currency_note",
            "Базовая валюта доступна только при первом запуске приложения.",
        ),
    )

    ttk.Label(
        currency_frame,
        text=tr("settings.currency.display_currency", "Валюта отображения:"),
        style="FormField.TLabel",
    ).grid(row=1, column=0, sticky="w", padx=pad_x, pady=pad_y)
    display_currency_combo = ttk.Combobox(
        currency_frame,
        textvariable=display_currency_var,
        values=context.controller.get_available_display_currencies(),
        state="readonly",
        width=18,
    )
    display_currency_combo.grid(row=1, column=1, sticky="ew", padx=(0, pad_x), pady=pad_y)
    enable_wayland_combobox_support(display_currency_combo)

    ttk.Label(
        currency_frame,
        text=tr("settings.currency.provider_mode", "Режим провайдера:"),
        style="FormField.TLabel",
    ).grid(row=2, column=0, sticky="w", padx=pad_x, pady=pad_y)
    provider_mode_combo = ttk.Combobox(
        currency_frame,
        textvariable=provider_mode_var,
        values=["personal", "commercial"],
        state="readonly",
        width=18,
    )
    provider_mode_combo.grid(row=2, column=1, sticky="ew", padx=(0, pad_x), pady=pad_y)
    enable_wayland_combobox_support(provider_mode_combo)

    ttk.Label(
        currency_frame,
        text=tr("settings.currency.primary_provider", "Основной провайдер:"),
        style="FormField.TLabel",
    ).grid(row=3, column=0, sticky="w", padx=pad_x, pady=pad_y)
    primary_provider_combo = ttk.Combobox(
        currency_frame,
        textvariable=primary_provider_var,
        values=state.provider_names,
        state="readonly",
        width=18,
    )
    primary_provider_combo.grid(row=3, column=1, sticky="ew", padx=(0, pad_x), pady=pad_y)
    enable_wayland_combobox_support(primary_provider_combo)

    ttk.Label(
        currency_frame,
        text=tr("settings.currency.fallback_provider", "Резервный провайдер:"),
        style="FormField.TLabel",
    ).grid(row=4, column=0, sticky="w", padx=pad_x, pady=pad_y)
    fallback_provider_combo = ttk.Combobox(
        currency_frame,
        textvariable=fallback_provider_var,
        values=state.provider_names,
        state="readonly",
        width=18,
    )
    fallback_provider_combo.grid(row=4, column=1, sticky="ew", padx=(0, pad_x), pady=pad_y)
    enable_wayland_combobox_support(fallback_provider_combo)

    ttk.Label(
        currency_frame,
        text=tr("settings.currency.exchange_api_key", "API key ExchangeRate:"),
        style="FormField.TLabel",
    ).grid(row=5, column=0, sticky="w", padx=pad_x, pady=pad_y)
    ttk.Entry(currency_frame, textvariable=exchange_api_key_var, width=24).grid(
        row=5, column=1, sticky="ew", padx=(0, pad_x), pady=pad_y
    )
    ttk.Label(
        currency_frame,
        text=tr(
            "settings.currency.api_key_storage",
            "Хранение API key: {label}",
            label=str(state.runtime_config.get("exchange_rate_api_key_storage_label", "") or ""),
        ),
        style="CardText.TLabel",
    ).grid(row=6, column=0, columnspan=2, sticky="w", padx=pad_x, pady=(0, pad_y))

    ttk.Checkbutton(
        currency_frame,
        text=tr("settings.currency.auto_update", "Автообновление курсов"),
        variable=auto_update_var,
        style="FormField.TCheckbutton",
    ).grid(row=7, column=0, columnspan=2, sticky="w", padx=pad_x, pady=(pad_y, 0))

    ttk.Label(
        currency_frame,
        text=tr("settings.currency.update_interval", "Интервал обновления (мин):"),
        style="FormField.TLabel",
    ).grid(row=8, column=0, sticky="w", padx=pad_x, pady=(pad_y, 0))
    ttk.Entry(currency_frame, textvariable=update_interval_var, width=24).grid(
        row=8, column=1, sticky="ew", padx=(0, pad_x), pady=pad_y
    )
    ttk.Label(
        currency_frame,
        text=tr(
            "settings.currency.security_diag",
            "Данные: {data_dir} | Режим: {mode}",
            data_dir=str(state.security_diagnostics.get("user_data_root", "") or ""),
            mode=(
                tr("settings.currency.mode.packaged", "packaged")
                if bool(state.security_diagnostics.get("packaged_mode", False))
                else tr("settings.currency.mode.source", "source")
            ),
        ),
        style="CardText.TLabel",
        wraplength=520,
        justify="left",
    ).grid(row=9, column=0, columnspan=2, sticky="w", padx=pad_x, pady=(0, pad_y))

    def _refresh_provider_choices(*_args: object) -> None:
        refresh_provider_choices(
            context=context,
            primary_provider_var=primary_provider_var,
            fallback_provider_var=fallback_provider_var,
            primary_provider_combo=primary_provider_combo,
            fallback_provider_combo=fallback_provider_combo,
        )

    def _save_currency_settings() -> None:
        save_currency_settings(
            context=context,
            messagebox_module=messagebox_module,
            display_currency_var=display_currency_var,
            provider_mode_var=provider_mode_var,
            primary_provider_var=primary_provider_var,
            fallback_provider_var=fallback_provider_var,
            exchange_api_key_var=exchange_api_key_var,
            auto_update_var=auto_update_var,
            update_interval_var=update_interval_var,
            display_currency_combo=display_currency_combo,
            refresh_provider_choices_callback=_refresh_provider_choices,
        )

    provider_mode_combo.bind("<<ComboboxSelected>>", _refresh_provider_choices, add="+")
    primary_provider_combo.bind("<<ComboboxSelected>>", _refresh_provider_choices, add="+")
    _refresh_provider_choices()

    buttons = ttk.Frame(currency_frame)
    buttons.grid(row=10, column=0, columnspan=2, sticky="ew", pady=(PAD_SM, 0))
    buttons.grid_columnconfigure(0, weight=1)
    ttk.Button(
        buttons,
        text=tr("common.save", "Сохранить"),
        style="Primary.TButton",
        command=_save_currency_settings,
    ).grid(row=0, column=0, sticky="ew")


def build_audit_section(
    left_panel: tk.Frame | ttk.Frame,
    *,
    parent: tk.Frame | ttk.Frame,
    context: Any,
    messagebox_module: MessageBoxLike = messagebox,
    row_index: int = 3,
) -> None:
    pad_x = PAD_SM
    pad_y = PAD_XS

    audit_card = create_card_section(left_panel, tr("settings.audit", "Финансовый аудит"))
    audit_card.grid(row=row_index, column=0, sticky="ew", pady=(PAD_LG, 0))
    audit_frame = audit_card.winfo_children()[-1]
    audit_frame.grid_columnconfigure(0, weight=1)

    def _on_run_audit() -> None:
        run_audit_action(
            context=context,
            parent=parent,
            messagebox_module=messagebox_module,
            show_audit_report_dialog=show_audit_report_dialog,
        )

    ttk.Button(
        audit_frame, text=tr("settings.audit.run", "Запустить аудит"), command=_on_run_audit
    ).grid(row=0, column=0, sticky="ew", padx=pad_x, pady=pad_y)
