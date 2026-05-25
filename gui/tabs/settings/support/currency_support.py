from __future__ import annotations

import logging
import tkinter as tk
from dataclasses import dataclass
from tkinter import ttk
from typing import Any

from domain.errors import DomainError
from gui.i18n import tr
from gui.logging_utils import log_ui_error

from .wallets_support import MessageBoxLike

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CurrencySectionState:
    runtime_config: dict[str, object]
    security_diagnostics: dict[str, object]
    provider_names: list[str]
    base_currency_text: str
    display_currency: str
    provider_mode: str
    primary_provider: str
    fallback_provider: str
    exchange_api_key: str
    auto_update: bool
    update_interval: str


def build_currency_section_state(context: Any) -> CurrencySectionState:
    runtime_config = context.controller.get_runtime_currency_config()
    security_diagnostics = context.controller.get_runtime_security_diagnostics()
    provider_names = context.controller.get_supported_currency_provider_names()
    display_currency_code = context.controller.get_display_currency_code()
    return CurrencySectionState(
        runtime_config=runtime_config,
        security_diagnostics=security_diagnostics,
        provider_names=provider_names,
        base_currency_text=str(runtime_config.get("base_currency", "KZT") or "KZT").upper(),
        display_currency=str(
            runtime_config.get("display_currency", display_currency_code) or display_currency_code
        ).upper(),
        provider_mode=str(runtime_config.get("provider_mode", "personal") or "personal").lower(),
        primary_provider=str(runtime_config.get("primary_provider", "") or "").lower(),
        fallback_provider=str(runtime_config.get("fallback_provider", "") or "").lower(),
        exchange_api_key=str(runtime_config.get("exchange_rate_api_key", "") or ""),
        auto_update=bool(runtime_config.get("auto_update", True)),
        update_interval=str(runtime_config.get("update_interval_minutes", 60) or 60),
    )


def refresh_provider_choices(
    *,
    context: Any,
    primary_provider_var: tk.StringVar,
    fallback_provider_var: tk.StringVar,
    primary_provider_combo: ttk.Combobox,
    fallback_provider_combo: ttk.Combobox,
) -> None:
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


def save_currency_settings(
    *,
    context: Any,
    messagebox_module: MessageBoxLike,
    display_currency_var: tk.StringVar,
    provider_mode_var: tk.StringVar,
    primary_provider_var: tk.StringVar,
    fallback_provider_var: tk.StringVar,
    exchange_api_key_var: tk.StringVar,
    auto_update_var: tk.BooleanVar,
    update_interval_var: tk.StringVar,
    display_currency_combo: ttk.Combobox,
    refresh_provider_choices_callback: Any,
) -> None:
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
    refresh_provider_choices_callback()
    context._refresh_list()
    context._refresh_charts()
    context._refresh_budgets()
    context._refresh_all()
    messagebox_module.showinfo(
        tr("common.done", "Готово"),
        tr("settings.currency.saved", "Настройки валюты сохранены."),
    )


def run_audit_action(
    *,
    context: Any,
    parent: tk.Frame | ttk.Frame,
    messagebox_module: MessageBoxLike,
    show_audit_report_dialog: Any,
) -> None:
    try:
        report = context.controller.run_audit()
        show_audit_report_dialog(report, parent)
    except (DomainError, ValueError, TypeError, RuntimeError) as error:
        log_ui_error(logger, "UI_SETTINGS_AUDIT_FAILED", error)
        messagebox_module.showerror(
            tr("settings.audit.error_title", "Ошибка аудита"),
            str(error),
        )
