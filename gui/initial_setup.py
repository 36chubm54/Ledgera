from __future__ import annotations

import logging
import os
import sqlite3
import tkinter as tk
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from tkinter import ttk
from typing import Any

from app.services import CurrencyService
from app_paths import get_icons_dir
from config import SQLITE_PATH
from gui.i18n import tr
from gui.shell.shell_window import apply_window_icon
from infrastructure.currency_providers import DEFAULT_PROVIDER_REGISTRY, CurrencyProviderRegistry

SUPPORTED_SETUP_CURRENCIES = ("KZT", "USD", "EUR", "RUB")
SETUP_PROVIDER_MODES = ("personal", "commercial")
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class InitialSetupSelection:
    base_currency: str
    display_currency: str
    provider_mode: str
    primary_provider: str
    fallback_provider: str
    exchange_rate_api_key: str
    auto_update: bool
    update_interval_minutes: int


@dataclass(frozen=True)
class InitialSetupOutcome:
    should_launch: bool
    initial_base_currency: str | None = None


def _quarantine_malformed_sqlite_file(db_path: Path) -> Path | None:
    if not db_path.exists():
        return None
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    quarantine_path = db_path.with_name(f"{db_path.name}.corrupt_{stamp}")
    try:
        os.replace(db_path, quarantine_path)
        logger.error(
            "Malformed SQLite file quarantined: source=%s quarantine=%s",
            db_path,
            quarantine_path,
        )
        return quarantine_path
    except OSError:
        logger.exception("Failed to quarantine malformed SQLite file: %s", db_path)
        return None


def _center_window_on_screen(window: tk.Tk | tk.Toplevel) -> None:
    window.update_idletasks()
    width = window.winfo_width()
    height = window.winfo_height()
    if width <= 1:
        width = window.winfo_reqwidth()
    if height <= 1:
        height = window.winfo_reqheight()
    screen_width = window.winfo_screenwidth()
    screen_height = window.winfo_screenheight()
    pos_x = max((screen_width - width) // 2, 0)
    pos_y = max((screen_height - height) // 2, 0)
    window.geometry(f"{width}x{height}+{pos_x}+{pos_y}")


def should_run_initial_setup(sqlite_path: str | Path = SQLITE_PATH) -> bool:
    db_path = Path(sqlite_path)
    if not db_path.exists():
        return True
    conn: sqlite3.Connection | None = None
    try:
        conn = sqlite3.connect(db_path)
        wallet_table = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'wallets'"
        ).fetchone()
        schema_meta_table = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'schema_meta'"
        ).fetchone()
        if wallet_table is None or schema_meta_table is None:
            return True
        base_currency_row = conn.execute(
            "SELECT value FROM schema_meta WHERE key = 'base_currency' LIMIT 1"
        ).fetchone()
        system_wallet_row = conn.execute(
            "SELECT 1 FROM wallets WHERE system = 1 OR id = 1 LIMIT 1"
        ).fetchone()
        base_currency = (
            str(base_currency_row[0]).strip().upper()
            if base_currency_row and base_currency_row[0] is not None
            else ""
        )
        return not (base_currency and system_wallet_row is not None)
    except sqlite3.Error:
        if conn is not None:
            conn.close()
        _quarantine_malformed_sqlite_file(db_path)
        return True
    finally:
        if conn is not None:
            conn.close()


def _supported_provider_names(
    base_currency: str,
    *,
    current_config: Mapping[str, object] | None = None,
    provider_registry: CurrencyProviderRegistry | None = None,
) -> tuple[str, ...]:
    registry = provider_registry or DEFAULT_PROVIDER_REGISTRY
    config = dict(CurrencyService.DEFAULT_CONFIG)
    if current_config is not None:
        config.update(dict(current_config))
    default_rates = CurrencyService.default_rates_for_base(base_currency)
    names: list[str] = []
    from infrastructure.currency_providers import ProviderBuildContext

    context = ProviderBuildContext(
        target_base=base_currency,
        config=config,
        default_rates=default_rates,
    )
    for name in registry.names():
        if registry.create(name, context) is not None:
            names.append(name)
    return tuple(names)


def _default_primary_provider(base_currency: str, available: tuple[str, ...]) -> str:
    if base_currency == "KZT":
        preferred = "nbk"
    elif base_currency == "RUB":
        preferred = "cbr"
    else:
        preferred = "exchange_rate"
    if preferred in available:
        return preferred
    if "exchange_rate" in available:
        return "exchange_rate"
    return available[0]


def _default_fallback_provider(primary: str, available: tuple[str, ...]) -> str:
    for candidate in ("exchange_rate", "static", "cbr", "nbk"):
        if candidate in available and candidate != primary:
            return candidate
    for candidate in available:
        if candidate != primary:
            return candidate
    return primary


def validate_initial_setup_selection(
    payload: InitialSetupSelection | Mapping[str, object],
    *,
    current_config: Mapping[str, object] | None = None,
    provider_registry: CurrencyProviderRegistry | None = None,
) -> InitialSetupSelection:
    raw: Mapping[str, object]
    if isinstance(payload, InitialSetupSelection):
        raw = payload.__dict__
    else:
        raw = payload

    base_currency = str(raw.get("base_currency", "") or "").strip().upper()
    display_currency = str(raw.get("display_currency", "") or "").strip().upper()
    provider_mode = str(raw.get("provider_mode", "") or "").strip().lower()
    primary_provider = str(raw.get("primary_provider", "") or "").strip().lower()
    fallback_provider = str(raw.get("fallback_provider", "") or "").strip().lower()
    exchange_rate_api_key = str(raw.get("exchange_rate_api_key", "") or "").strip()
    auto_update = bool(raw.get("auto_update", False))
    update_interval_raw = raw.get("update_interval_minutes", 60)
    update_interval_minutes = CurrencyService.parse_update_interval_minutes(update_interval_raw)

    if base_currency not in SUPPORTED_SETUP_CURRENCIES:
        raise ValueError("Unsupported base currency")
    if display_currency not in SUPPORTED_SETUP_CURRENCIES:
        raise ValueError("Unsupported display currency")
    if provider_mode not in SETUP_PROVIDER_MODES:
        raise ValueError("Unsupported provider mode")

    default_rates = CurrencyService.default_rates_for_base(base_currency)
    if display_currency != base_currency and display_currency not in default_rates:
        raise ValueError("Display currency is not supported for the selected base currency")

    available_providers = _supported_provider_names(
        base_currency,
        current_config=current_config,
        provider_registry=provider_registry,
    )
    if primary_provider not in available_providers:
        raise ValueError("Unsupported primary provider")
    if fallback_provider not in available_providers:
        raise ValueError("Unsupported fallback provider")
    if primary_provider == fallback_provider:
        raise ValueError("Primary and fallback providers must be different")
    return InitialSetupSelection(
        base_currency=base_currency,
        display_currency=display_currency,
        provider_mode=provider_mode,
        primary_provider=primary_provider,
        fallback_provider=fallback_provider,
        exchange_rate_api_key=exchange_rate_api_key,
        auto_update=auto_update,
        update_interval_minutes=update_interval_minutes,
    )


def build_initial_currency_config(
    selection: InitialSetupSelection,
    *,
    current_config: Mapping[str, object] | None = None,
) -> dict[str, object]:
    config = dict(CurrencyService.DEFAULT_CONFIG)
    if current_config is not None:
        config.update(dict(current_config))
    active_fallback_key = (
        "commercial_fallback_provider"
        if selection.provider_mode == "commercial"
        else "fallback_provider"
    )
    config.update(
        {
            "base_currency": selection.base_currency,
            "display_currency": selection.display_currency,
            "provider_mode": selection.provider_mode,
            "primary_provider": selection.primary_provider,
            active_fallback_key: selection.fallback_provider,
            "exchange_rate_api_key": selection.exchange_rate_api_key,
            "auto_update": selection.auto_update,
            "update_interval_minutes": selection.update_interval_minutes,
        }
    )
    return config


def ensure_initial_setup(
    *,
    sqlite_path: str | Path = SQLITE_PATH,
    config_file: Path | None = None,
    provider_registry: CurrencyProviderRegistry | None = None,
    setup_runner: Callable[..., InitialSetupSelection | Mapping[str, object] | None] | None = None,
) -> InitialSetupOutcome:
    if not should_run_initial_setup(sqlite_path):
        return InitialSetupOutcome(should_launch=True, initial_base_currency=None)

    current_config = CurrencyService.load_config_payload(
        config_file=config_file,
        use_env_override=False,
    )
    runner = setup_runner or run_initial_setup_wizard
    payload = runner(
        current_config=current_config,
        provider_registry=provider_registry or DEFAULT_PROVIDER_REGISTRY,
    )
    if payload is None:
        return InitialSetupOutcome(should_launch=False, initial_base_currency=None)

    selection = validate_initial_setup_selection(
        payload,
        current_config=current_config,
        provider_registry=provider_registry,
    )
    config = build_initial_currency_config(selection, current_config=current_config)
    CurrencyService.save_config_payload(config, config_file=config_file)
    return InitialSetupOutcome(
        should_launch=True,
        initial_base_currency=selection.base_currency,
    )


def run_initial_setup_wizard(
    *,
    current_config: Mapping[str, object] | None = None,
    provider_registry: CurrencyProviderRegistry | None = None,
) -> InitialSetupSelection | None:
    config = dict(CurrencyService.DEFAULT_CONFIG)
    if current_config is not None:
        config.update(dict(current_config))

    base_currency = str(config.get("base_currency", "KZT") or "KZT").strip().upper()
    if base_currency not in SUPPORTED_SETUP_CURRENCIES:
        base_currency = "KZT"
    display_currency = (
        str(config.get("display_currency", base_currency) or base_currency).strip().upper()
    )
    if display_currency not in SUPPORTED_SETUP_CURRENCIES:
        display_currency = base_currency

    root = tk.Tk()
    root.title(tr("setup.title", "Первоначальная настройка"))
    root.resizable(False, False)
    root.grid_columnconfigure(0, weight=1)
    apply_window_icon(root, icons_dir=get_icons_dir())

    content = ttk.Frame(root, padding=16)
    content.grid(row=0, column=0, sticky="nsew")
    content.grid_columnconfigure(1, weight=1)

    ttk.Label(
        content,
        text=tr(
            "setup.summary",
            "Настройте базовую валюту и параметры поставщика курсов перед первым запуском.",
        ),
        wraplength=460,
        justify="left",
    ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))

    base_var = tk.StringVar(value=base_currency)
    display_var = tk.StringVar(value=display_currency)
    provider_mode_var = tk.StringVar(
        value=str(config.get("provider_mode", "personal") or "personal")
    )
    primary_provider_var = tk.StringVar(value=str(config.get("primary_provider", "") or ""))
    fallback_provider_var = tk.StringVar(value=str(config.get("fallback_provider", "") or ""))
    api_key_var = tk.StringVar(value=str(config.get("exchange_rate_api_key", "") or ""))
    auto_update_var = tk.BooleanVar(value=bool(config.get("auto_update", True)))
    update_interval_var = tk.StringVar(
        value=str(
            CurrencyService._normalize_update_interval_minutes(
                config.get("update_interval_minutes", 60)
            )
        )
    )
    error_var = tk.StringVar(value="")

    row = 1

    def _add_label(key: str, default: str) -> None:
        nonlocal row
        ttk.Label(content, text=tr(key, default)).grid(
            row=row,
            column=0,
            sticky="w",
            pady=4,
            padx=(0, 12),
        )

    def _add_combo(variable: tk.StringVar, values: tuple[str, ...]) -> ttk.Combobox:
        combo = ttk.Combobox(
            content,
            textvariable=variable,
            values=list(values),
            state="readonly",
            width=28,
        )
        combo.grid(row=row, column=1, sticky="ew", pady=4)
        return combo

    _add_label("setup.base_currency", "Базовая валюта")
    base_combo = _add_combo(base_var, SUPPORTED_SETUP_CURRENCIES)
    row += 1

    _add_label("setup.display_currency", "Валюта отображения")
    _add_combo(display_var, SUPPORTED_SETUP_CURRENCIES)
    row += 1

    _add_label("setup.provider_mode", "Режим провайдера")
    _add_combo(provider_mode_var, SETUP_PROVIDER_MODES)
    row += 1

    _add_label("setup.primary_provider", "Основной провайдер")
    primary_combo = _add_combo(primary_provider_var, ("",))
    row += 1

    _add_label("setup.fallback_provider", "Резервный провайдер")
    fallback_combo = _add_combo(fallback_provider_var, ("",))
    row += 1

    _add_label("setup.exchange_api_key", "API key ExchangeRate")
    ttk.Entry(content, textvariable=api_key_var, width=32, show="").grid(
        row=row,
        column=1,
        sticky="ew",
        pady=4,
    )
    row += 1

    ttk.Checkbutton(
        content,
        text=tr("setup.auto_update", "Автообновление курсов"),
        variable=auto_update_var,
    ).grid(row=row, column=0, columnspan=2, sticky="w", pady=(8, 4))
    row += 1

    _add_label("setup.update_interval", "Интервал обновления (мин)")
    ttk.Entry(content, textvariable=update_interval_var, width=32).grid(
        row=row,
        column=1,
        sticky="ew",
        pady=4,
    )
    row += 1

    ttk.Label(content, textvariable=error_var, foreground="#b3261e", wraplength=460).grid(
        row=row,
        column=0,
        columnspan=2,
        sticky="w",
        pady=(4, 8),
    )
    row += 1

    result: InitialSetupSelection | None = None

    def _refresh_provider_choices(*_args: Any) -> None:
        available = _supported_provider_names(
            base_var.get(),
            current_config=config,
            provider_registry=provider_registry,
        )
        primary_values = available
        current_primary = primary_provider_var.get().strip().lower()
        preferred_primary = _default_primary_provider(base_var.get(), available)
        if current_primary not in primary_values:
            primary_provider_var.set(preferred_primary)
        primary_combo.config(values=list(primary_values))

        current_primary = primary_provider_var.get().strip().lower()
        fallback_values = tuple(name for name in available if name != current_primary) or available
        current_fallback = fallback_provider_var.get().strip().lower()
        preferred_fallback = _default_fallback_provider(current_primary, available)
        if current_fallback not in fallback_values:
            fallback_provider_var.set(preferred_fallback)
        fallback_combo.config(values=list(fallback_values))

        if display_var.get().strip().upper() not in SUPPORTED_SETUP_CURRENCIES:
            display_var.set(base_var.get().strip().upper())

    base_combo.bind("<<ComboboxSelected>>", _refresh_provider_choices, add="+")
    primary_combo.bind("<<ComboboxSelected>>", _refresh_provider_choices, add="+")
    _refresh_provider_choices()

    buttons = ttk.Frame(content)
    buttons.grid(row=row, column=0, columnspan=2, sticky="e", pady=(4, 0))
    row += 1

    def _cancel() -> None:
        root.destroy()

    def _save() -> None:
        nonlocal result
        try:
            result = validate_initial_setup_selection(
                {
                    "base_currency": base_var.get(),
                    "display_currency": display_var.get(),
                    "provider_mode": provider_mode_var.get(),
                    "primary_provider": primary_provider_var.get(),
                    "fallback_provider": fallback_provider_var.get(),
                    "exchange_rate_api_key": api_key_var.get(),
                    "auto_update": auto_update_var.get(),
                    "update_interval_minutes": update_interval_var.get(),
                },
                current_config=config,
                provider_registry=provider_registry,
            )
        except ValueError as exc:
            error_var.set(str(exc))
            return
        root.destroy()

    ttk.Button(buttons, text=tr("common.cancel", "Отмена"), command=_cancel).grid(
        row=0,
        column=0,
        padx=(0, 8),
    )
    ttk.Button(buttons, text=tr("common.save", "Сохранить"), command=_save).grid(
        row=0,
        column=1,
    )

    root.protocol("WM_DELETE_WINDOW", _cancel)
    _center_window_on_screen(root)
    root.mainloop()
    return result
