from __future__ import annotations

import logging
import tkinter as tk
from tkinter import ttk
from typing import Any

from domain.errors import DomainError
from gui.i18n import tr
from gui.logging_utils import log_ui_error
from gui.tooltip import Tooltip
from gui.ui_dialogs import messagebox_compat as messagebox
from gui.ui_theme import PAD_LG, PAD_SM, PAD_XS, create_card_section

from .audit_dialog import show_audit_report_dialog
from .wallets_section import MessageBoxLike

logger = logging.getLogger(__name__)


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

    runtime_config = context.controller.get_runtime_currency_config()
    security_diagnostics = context.controller.get_runtime_security_diagnostics()
    provider_names = context.controller.get_supported_currency_provider_names()

    base_currency_text = str(runtime_config.get("base_currency", "KZT") or "KZT").upper()
    display_currency_var = tk.StringVar(
        value=str(
            runtime_config.get("display_currency", context.controller.get_display_currency_code())
            or context.controller.get_display_currency_code()
        ).upper()
    )
    provider_mode_var = tk.StringVar(
        value=str(runtime_config.get("provider_mode", "personal") or "personal").lower()
    )
    primary_provider_var = tk.StringVar(
        value=str(runtime_config.get("primary_provider", "") or "").lower()
    )
    fallback_provider_var = tk.StringVar(
        value=str(runtime_config.get("fallback_provider", "") or "").lower()
    )
    exchange_api_key_var = tk.StringVar(
        value=str(runtime_config.get("exchange_rate_api_key", "") or "")
    )
    auto_update_var = tk.BooleanVar(value=bool(runtime_config.get("auto_update", True)))
    update_interval_var = tk.StringVar(
        value=str(runtime_config.get("update_interval_minutes", 60) or 60)
    )

    ttk.Label(
        currency_frame,
        text=tr("settings.currency.base_currency", "Базовая валюта:"),
        style="FormField.TLabel",
    ).grid(row=0, column=0, sticky="w", padx=pad_x, pady=pad_y)
    base_currency_frame = ttk.Frame(currency_frame, style="CardBody.TFrame")
    base_currency_frame.grid(row=0, column=1, sticky="w", padx=(0, pad_x), pady=pad_y)
    ttk.Label(
        base_currency_frame,
        text=base_currency_text,
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

    ttk.Label(
        currency_frame,
        text=tr("settings.currency.primary_provider", "Основной провайдер:"),
        style="FormField.TLabel",
    ).grid(row=3, column=0, sticky="w", padx=pad_x, pady=pad_y)
    primary_provider_combo = ttk.Combobox(
        currency_frame,
        textvariable=primary_provider_var,
        values=provider_names,
        state="readonly",
        width=18,
    )
    primary_provider_combo.grid(row=3, column=1, sticky="ew", padx=(0, pad_x), pady=pad_y)

    ttk.Label(
        currency_frame,
        text=tr("settings.currency.fallback_provider", "Резервный провайдер:"),
        style="FormField.TLabel",
    ).grid(row=4, column=0, sticky="w", padx=pad_x, pady=pad_y)
    fallback_provider_combo = ttk.Combobox(
        currency_frame,
        textvariable=fallback_provider_var,
        values=provider_names,
        state="readonly",
        width=18,
    )
    fallback_provider_combo.grid(row=4, column=1, sticky="ew", padx=(0, pad_x), pady=pad_y)

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
            label=str(runtime_config.get("exchange_rate_api_key_storage_label", "") or ""),
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
            data_dir=str(security_diagnostics.get("user_data_root", "") or ""),
            mode=(
                tr("settings.currency.mode.packaged", "packaged")
                if bool(security_diagnostics.get("packaged_mode", False))
                else tr("settings.currency.mode.source", "source")
            ),
        ),
        style="CardText.TLabel",
        wraplength=520,
        justify="left",
    ).grid(row=9, column=0, columnspan=2, sticky="w", padx=pad_x, pady=(0, pad_y))

    def _refresh_provider_choices(*_args: object) -> None:
        available = context.controller.get_supported_currency_provider_names()
        current_primary = str(primary_provider_var.get() or "").strip().lower()
        if current_primary not in available:
            current_primary = available[0] if available else ""
            primary_provider_var.set(current_primary)
        primary_provider_combo.config(values=available)

        fallback_values = [name for name in available if name != current_primary] or available
        current_fallback = str(fallback_provider_var.get() or "").strip().lower()
        if current_fallback not in fallback_values:
            for candidate in ("exchange_rate", "static", "cbr", "nbk"):
                if candidate in fallback_values:
                    current_fallback = candidate
                    break
            if not current_fallback and fallback_values:
                current_fallback = fallback_values[0]
            fallback_provider_var.set(current_fallback)
        fallback_provider_combo.config(values=fallback_values)

    def _save_currency_settings() -> None:
        try:
            context.controller.update_runtime_currency_config(
                display_currency=str(display_currency_var.get() or ""),
                provider_mode=str(provider_mode_var.get() or ""),
                primary_provider=str(primary_provider_var.get() or ""),
                fallback_provider=str(fallback_provider_var.get() or ""),
                exchange_rate_api_key=str(exchange_api_key_var.get() or ""),
                auto_update=auto_update_var.get(),
                update_interval_minutes=str(update_interval_var.get() or ""),
            )
        except (ValueError, RuntimeError) as error:
            log_ui_error(logger, "UI_SETTINGS_UPDATE_CURRENCY_CONFIG_FAILED", error)
            messagebox_module.showerror(
                tr("common.error", "Ошибка"),
                tr(
                    "settings.currency.error.save",
                    "Не удалось сохранить настройки валюты: {error}",
                    error=str(error),
                ),
            )
            return

        display_currency_combo.config(values=context.controller.get_available_display_currencies())
        _refresh_provider_choices()
        context._refresh_list()
        context._refresh_charts()
        context._refresh_budgets()
        context._refresh_all()
        messagebox_module.showinfo(
            tr("common.done", "Готово"),
            tr("settings.currency.saved", "Настройки валюты сохранены."),
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
        try:
            report = context.controller.run_audit()
            show_audit_report_dialog(report, parent)
        except (DomainError, ValueError, TypeError, RuntimeError) as error:
            log_ui_error(logger, "UI_SETTINGS_AUDIT_FAILED", error)
            messagebox_module.showerror(
                tr("settings.audit.error_title", "Ошибка аудита"), str(error)
            )

    ttk.Button(
        audit_frame, text=tr("settings.audit.run", "Запустить аудит"), command=_on_run_audit
    ).grid(row=0, column=0, sticky="ew", padx=pad_x, pady=pad_y)
