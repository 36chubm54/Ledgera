from __future__ import annotations

import logging
import os
import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass
from tkinter import filedialog, ttk
from typing import Any, Protocol

from domain.errors import DomainError
from domain.import_policy import ImportPolicy
from domain.import_result import ImportResult
from gui.helpers import open_in_file_manager
from gui.i18n import tr
from gui.logging_utils import log_ui_error
from gui.tabs.settings_support import show_audit_report_dialog
from gui.tooltip import Tooltip
from gui.ui_dialogs import messagebox_compat as messagebox
from gui.ui_helpers import attach_treeview_scrollbars, enable_treeview_column_autosize
from gui.ui_theme import (
    PAD_LG,
    PAD_SM,
    PAD_XS,
    create_card_section,
    enable_treeview_zebra,
)


@dataclass(slots=True)
class WalletsSectionBindings:
    refresh_wallets: Callable[[], None]


@dataclass(slots=True)
class WalletFormFields:
    name_entry: ttk.Entry
    currency_entry: ttk.Entry
    initial_entry: ttk.Entry
    allow_negative_var: tk.BooleanVar


logger = logging.getLogger(__name__)


class MessageBoxLike(Protocol):
    def showerror(self, title: str, message: str) -> Any: ...

    def showinfo(self, title: str, message: str) -> Any: ...

    def askyesno(self, title: str, message: str) -> bool: ...


def refresh_wallet_related_ui(context: Any) -> None:
    if context.refresh_transfer_wallet_menus is not None:
        try:
            context.refresh_transfer_wallet_menus()
        except tk.TclError:
            pass

    if context.refresh_operation_wallet_menu is not None:
        try:
            context.refresh_operation_wallet_menu()
        except tk.TclError:
            pass


def _create_wallet_form(
    parent: tk.Misc,
    *,
    base_currency_code: str,
    pad_x: int,
    pad_y: int,
    label_style: str = "TLabel",
    checkbutton_style: str = "TCheckbutton",
) -> WalletFormFields:
    form = ttk.Frame(parent)
    form.grid(row=0, column=0, sticky="ew", padx=pad_x, pady=pad_y)
    form.grid_columnconfigure(1, weight=1)

    ttk.Label(
        form,
        text=tr("settings.wallets.name", "Название:"),
        style=label_style,
    ).grid(row=0, column=0, sticky="w")
    wallet_name_entry = ttk.Entry(form)
    wallet_name_entry.grid(row=0, column=1, sticky="ew", pady=2)

    ttk.Label(
        form,
        text=tr("settings.wallets.currency", "Валюта:"),
        style=label_style,
    ).grid(row=1, column=0, sticky="w")
    wallet_currency_entry = ttk.Entry(form, width=8)
    wallet_currency_entry.insert(0, base_currency_code)
    wallet_currency_entry.grid(row=1, column=1, sticky="ew", pady=2)

    ttk.Label(
        form,
        text=tr("settings.wallets.initial_balance", "Начальный баланс:"),
        style=label_style,
    ).grid(row=2, column=0, sticky="w")
    wallet_initial_entry = ttk.Entry(form)
    wallet_initial_entry.insert(0, "0")
    wallet_initial_entry.grid(row=2, column=1, sticky="ew", pady=2)

    wallet_allow_negative_var = tk.BooleanVar(value=False)
    ttk.Checkbutton(
        form,
        text=tr("settings.wallets.allow_negative", "Разрешить отрицательный баланс"),
        variable=wallet_allow_negative_var,
        style=checkbutton_style,
    ).grid(
        row=3,
        column=0,
        columnspan=2,
        sticky="w",
        pady=2,
    )
    return WalletFormFields(
        name_entry=wallet_name_entry,
        currency_entry=wallet_currency_entry,
        initial_entry=wallet_initial_entry,
        allow_negative_var=wallet_allow_negative_var,
    )


def _build_wallet_tree(
    parent: tk.Misc,
    *,
    pad_x: int,
) -> tuple[ttk.Treeview, ttk.Scrollbar | None, ttk.Scrollbar | None]:
    list_frame = ttk.Frame(parent)
    list_frame.grid(row=1, column=0, sticky="nsew", padx=pad_x)
    list_frame.grid_rowconfigure(0, weight=1)
    list_frame.grid_columnconfigure(0, weight=1)

    wallet_columns = (
        "id",
        "name",
        "currency",
        "initial_balance",
        "balance",
        "allow_negative",
        "active",
    )
    wallet_tree = ttk.Treeview(
        list_frame,
        columns=wallet_columns,
        show="headings",
        selectmode="browse",
        height=8,
    )
    enable_treeview_zebra(wallet_tree)
    for col, text, width, minwidth, stretch, anchor in (
        ("id", "ID", 40, 40, False, "e"),
        ("name", tr("settings.wallets.name_short", "Название"), 100, 100, True, "w"),
        ("currency", tr("settings.wallets.currency_short", "Вал."), 60, 60, False, "center"),
        (
            "initial_balance",
            tr("settings.wallets.initial_balance_short", "Старт"),
            110,
            90,
            False,
            "e",
        ),
        ("balance", tr("settings.wallets.balance", "Баланс"), 110, 90, False, "e"),
        (
            "allow_negative",
            tr("settings.wallets.allow_negative_short", "Минус"),
            92,
            92,
            False,
            "center",
        ),
        ("active", tr("settings.wallets.active", "Активен"), 90, 90, False, "center"),
    ):
        wallet_tree.heading(col, text=text)
        wallet_tree.column(col, width=width, minwidth=minwidth, stretch=stretch, anchor=anchor)  # type: ignore[arg-type]
    enable_treeview_column_autosize(wallet_tree, columns=("name",), max_width=320)
    wallet_tree.grid(row=0, column=0, sticky="nsew")
    wallet_scroll, wallet_xscroll = attach_treeview_scrollbars(
        list_frame, wallet_tree, row=0, column=0, horizontal=True
    )
    return wallet_tree, wallet_scroll, wallet_xscroll


def _bind_wallet_scrolling(
    wallet_tree: ttk.Treeview,
    wallet_scroll: ttk.Scrollbar | None,
    wallet_xscroll: ttk.Scrollbar | None,
) -> None:
    def _wallet_scroll_units(delta: int, *, multiplier: int = 12) -> int:
        if delta == 0:
            return 0
        base_units = max(1, abs(int(delta)) // 120)
        return base_units * multiplier

    def _scroll_wallet_vertically(direction: int, units: int) -> str:
        wallet_tree.yview_scroll(direction * units, "units")
        return "break"

    def _scroll_wallet_horizontally(direction: int, units: int) -> str:
        wallet_tree.xview_scroll(direction * units, "units")
        return "break"

    def _on_wallet_mousewheel(event: tk.Event) -> str:
        delta = int(getattr(event, "delta", 0))
        units = _wallet_scroll_units(delta, multiplier=8)
        if units <= 0:
            return "break"
        direction = -1 if delta > 0 else 1
        return _scroll_wallet_vertically(direction, units)

    def _on_wallet_shift_mousewheel(event: tk.Event) -> str:
        delta = int(getattr(event, "delta", 0))
        units = _wallet_scroll_units(delta, multiplier=12)
        if units <= 0:
            return "break"
        direction = -1 if delta > 0 else 1
        return _scroll_wallet_horizontally(direction, units)

    def _on_wallet_button4(_event: tk.Event) -> str:
        return _scroll_wallet_vertically(-1, 3)

    def _on_wallet_button5(_event: tk.Event) -> str:
        return _scroll_wallet_vertically(1, 3)

    def _on_wallet_shift_button4(_event: tk.Event) -> str:
        return _scroll_wallet_horizontally(-1, 3)

    def _on_wallet_shift_button5(_event: tk.Event) -> str:
        return _scroll_wallet_horizontally(1, 3)

    for widget in (wallet_tree, wallet_scroll, wallet_xscroll):
        if widget is not None:
            widget.bind("<MouseWheel>", _on_wallet_mousewheel, add="+")
            widget.bind("<Shift-MouseWheel>", _on_wallet_shift_mousewheel, add="+")
            widget.bind("<Button-4>", _on_wallet_button4, add="+")
            widget.bind("<Button-5>", _on_wallet_button5, add="+")
            widget.bind("<Shift-Button-4>", _on_wallet_shift_button4, add="+")
            widget.bind("<Shift-Button-5>", _on_wallet_shift_button5, add="+")


def _build_wallet_actions(
    parent: tk.Misc,
    *,
    pad_x: int,
    pad_y: int,
    on_delete: Callable[[], None],
    on_refresh: Callable[[], None],
    on_close: Callable[[], None] | None,
) -> None:
    wallet_actions = ttk.Frame(parent)
    wallet_actions.grid(row=2, column=0, sticky="ew", padx=pad_x, pady=pad_y)
    wallet_actions.grid_columnconfigure(0, weight=1)
    wallet_actions.grid_columnconfigure(1, weight=1)
    if on_close is not None:
        wallet_actions.grid_columnconfigure(2, weight=1)

    ttk.Button(
        wallet_actions,
        text=tr("settings.wallets.delete", "Удалить кошелек"),
        command=on_delete,
    ).grid(
        row=0,
        column=0,
        sticky="ew",
        padx=(0, 4),
    )
    ttk.Button(
        wallet_actions,
        text=tr("common.refresh", "Обновить"),
        command=on_refresh,
    ).grid(
        row=0,
        column=1,
        sticky="ew",
        padx=(4, 0),
    )
    if on_close is not None:
        ttk.Button(
            wallet_actions,
            text=tr("common.close", "Закрыть"),
            command=on_close,
        ).grid(
            row=0,
            column=2,
            sticky="ew",
            padx=(8, 0),
        )


def build_wallets_section(
    parent_panel: tk.Frame | ttk.Frame,
    *,
    context: Any,
    base_currency_code: str,
    messagebox_module: MessageBoxLike = messagebox,
    use_card: bool = True,
    row_index: int = 0,
    on_close: Callable[[], None] | None = None,
) -> WalletsSectionBindings:
    pad_x = PAD_SM
    pad_y = PAD_XS

    if use_card:
        wallets_card = create_card_section(parent_panel, tr("settings.wallets", "Кошельки"))
        wallets_card.grid(row=row_index, column=0, sticky="nsew", pady=(0, PAD_LG))
        wallets_frame = wallets_card.winfo_children()[-1]
    else:
        wallets_frame = ttk.Frame(parent_panel)
        wallets_frame.grid(row=row_index, column=0, sticky="nsew")
    wallets_frame.grid_columnconfigure(0, weight=1)
    wallets_frame.grid_rowconfigure(1, weight=1)
    form_fields = _create_wallet_form(
        wallets_frame,
        base_currency_code=base_currency_code,
        pad_x=pad_x,
        pad_y=pad_y,
        label_style="FormField.TLabel" if use_card else "TLabel",
        checkbutton_style="FormField.TCheckbutton" if use_card else "TCheckbutton",
    )
    wallet_tree, wallet_scroll, wallet_xscroll = _build_wallet_tree(wallets_frame, pad_x=pad_x)
    _bind_wallet_scrolling(wallet_tree, wallet_scroll, wallet_xscroll)

    def refresh_wallets() -> None:
        for iid in wallet_tree.get_children():
            wallet_tree.delete(iid)
        for wallet in context.controller.load_wallets():
            try:
                balance = context.controller.wallet_balance(wallet.id)
            except ValueError:
                balance = wallet.initial_balance
            wallet_tree.insert(
                "",
                tk.END,
                values=(
                    int(wallet.id),
                    str(wallet.name),
                    str(wallet.currency),
                    f"{wallet.initial_balance:.2f}",
                    f"{balance:.2f}",
                    tr("common.yes", "Да") if wallet.allow_negative else tr("common.no", "Нет"),
                    tr("common.yes", "Да") if wallet.is_active else tr("common.no", "Нет"),
                ),
            )
        refresh_wallet_related_ui(context)

    context.refresh_wallets = refresh_wallets

    def create_wallet() -> None:
        try:
            initial_balance = float(form_fields.initial_entry.get().strip() or "0")
        except ValueError:
            messagebox_module.showerror(
                tr("common.error", "Ошибка"),
                tr(
                    "settings.wallets.error.initial_balance",
                    "Некорректный начальный баланс кошелька.",
                ),
            )
            return

        name = ""
        try:
            name = form_fields.name_entry.get().strip()
            wallet = context.controller.create_wallet(
                name=name,
                currency=(form_fields.currency_entry.get() or base_currency_code).strip(),
                initial_balance=initial_balance,
                allow_negative=form_fields.allow_negative_var.get(),
            )
            messagebox_module.showinfo(
                tr("common.done", "Готово"),
                tr(
                    "settings.wallets.created",
                    "Кошелек создан: [{wallet_id}] {wallet_name}",
                    wallet_id=wallet.id,
                    wallet_name=wallet.name,
                ),
            )
            form_fields.name_entry.delete(0, tk.END)
            form_fields.initial_entry.delete(0, tk.END)
            form_fields.initial_entry.insert(0, "0")
            refresh_wallets()
        except (DomainError, ValueError, TypeError, RuntimeError) as error:
            log_ui_error(logger, "UI_SETTINGS_CREATE_WALLET_FAILED", error, name=name)
            messagebox_module.showerror(
                tr("common.error", "Ошибка"),
                tr(
                    "settings.wallets.error.create",
                    "Не удалось создать кошелек: {error}",
                    error=str(error),
                ),
            )

    ttk.Button(
        form_fields.name_entry.master,
        text=tr("settings.wallets.create", "Создать кошелек"),
        style="Primary.TButton",
        command=create_wallet,
    ).grid(
        row=4,
        column=0,
        columnspan=2,
        sticky="ew",
        pady=(6, 0),
    )

    def delete_wallet() -> None:
        selection = wallet_tree.selection()
        if not selection:
            messagebox_module.showerror(
                tr("common.error", "Ошибка"),
                tr("settings.wallets.error.select_delete", "Выберите кошелек для удаления."),
            )
            return
        try:
            values = wallet_tree.item(selection[0], "values")
            wallet_id = int(values[0])
        except (TypeError, ValueError, IndexError):
            messagebox_module.showerror(
                tr("common.error", "Ошибка"),
                tr(
                    "settings.wallets.error.parse_id",
                    "Не удалось определить идентификатор выбранного кошелька.",
                ),
            )
            return

        try:
            context.controller.soft_delete_wallet(wallet_id)
            messagebox_module.showinfo(
                tr("common.done", "Готово"),
                tr("settings.wallets.deleted", "Кошелек деактивирован."),
            )
            refresh_wallets()
        except (DomainError, ValueError, TypeError, RuntimeError) as error:
            log_ui_error(logger, "UI_SETTINGS_DELETE_WALLET_FAILED", error, wallet_id=wallet_id)
            messagebox_module.showerror(tr("common.error", "Ошибка"), str(error))

    _build_wallet_actions(
        wallets_frame,
        pad_x=pad_x,
        pad_y=pad_y,
        on_delete=delete_wallet,
        on_refresh=refresh_wallets,
        on_close=on_close,
    )

    return WalletsSectionBindings(refresh_wallets=refresh_wallets)


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
    ttk.Entry(
        currency_frame,
        textvariable=exchange_api_key_var,
        width=24,
    ).grid(row=5, column=1, sticky="ew", padx=(0, pad_x), pady=pad_y)

    ttk.Checkbutton(
        currency_frame,
        text=tr("settings.currency.auto_update", "Автообновление курсов"),
        variable=auto_update_var,
        style="FormField.TCheckbutton",
    ).grid(row=6, column=0, columnspan=2, sticky="w", padx=pad_x, pady=(pad_y, 0))

    ttk.Label(
        currency_frame,
        text=tr("settings.currency.update_interval", "Интервал обновления (мин):"),
        style="FormField.TLabel",
    ).grid(row=7, column=0, sticky="w", padx=pad_x, pady=(pad_y, 0))
    ttk.Entry(
        currency_frame,
        textvariable=update_interval_var,
        width=24,
    ).grid(row=7, column=1, sticky="ew", padx=(0, pad_x), pady=pad_y)

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
    buttons.grid(row=8, column=0, columnspan=2, sticky="ew", pady=(PAD_SM, 0))
    buttons.grid_columnconfigure(0, weight=1)
    ttk.Button(
        buttons,
        text=tr("common.save", "Сохранить"),
        style="Primary.TButton",
        command=_save_currency_settings,
    ).grid(row=0, column=0, sticky="ew")


def build_backup_section(
    left_panel: tk.Frame | ttk.Frame,
    *,
    parent: tk.Frame | ttk.Frame,
    context: Any,
    refresh_wallets: Callable[[], None],
    messagebox_module: MessageBoxLike = messagebox,
    row_index: int = 2,
) -> None:
    pad_x = PAD_SM
    pad_y = PAD_XS

    backup_card = create_card_section(left_panel, tr("settings.backup", "Резервная копия (JSON)"))
    backup_card.grid(row=row_index, column=0, sticky="ew")
    backup_frame = backup_card.winfo_children()[-1]
    backup_frame.grid_columnconfigure(0, weight=1)
    backup_frame.grid_columnconfigure(1, weight=1)

    def _refresh_mandatory_if_available() -> None:
        refresh_mandatory = getattr(context, "refresh_mandatory", None)
        if callable(refresh_mandatory):
            refresh_mandatory()

    def import_backup() -> None:
        filepath = filedialog.askopenfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            title=tr("settings.backup.import.title", "Импорт полной копии"),
        )
        if not filepath:
            return

        if not messagebox_module.askyesno(
            tr("common.confirm", "Подтверждение"),
            tr(
                "settings.backup.import.confirm",
                "Это заменит все кошельки, записи, переводы, обязательные расходы, "
                "бюджеты и данные распределения. Продолжить?",
            ),
        ):
            return

        def task(force: bool) -> ImportResult:
            return context.controller.import_records(
                "JSON",
                filepath,
                ImportPolicy.FULL_BACKUP,
                force=force,
            )

        def on_success(result: ImportResult) -> None:
            details = ""
            if result.skipped:
                details = f"\nSkipped: {result.skipped}\n- " + "\n- ".join(result.errors[:5])
            messagebox_module.showinfo(
                tr("common.done", "Готово"),
                tr(
                    "settings.backup.import.success",
                    "Резервная копия импортирована. Импортировано сущностей: {count}.{details}",
                    count=result.imported,
                    details=details,
                ),
            )
            _refresh_mandatory_if_available()
            refresh_wallets()
            context._refresh_list()
            context._refresh_charts()
            context._refresh_budgets()
            context._refresh_all()

        def run_import(force: bool) -> None:
            def current_task() -> ImportResult:
                return task(force)

            def on_error(exc: BaseException) -> None:
                try:
                    from utils.backup_utils import BackupReadonlyError

                    is_readonly = isinstance(exc, BackupReadonlyError)
                except ImportError:
                    is_readonly = False

                if is_readonly and not force:
                    if messagebox_module.askyesno(
                        tr("settings.backup.readonly.title", "Снимок только для чтения"),
                        tr(
                            "settings.backup.readonly.confirm",
                            "Резервная копия доступна только для чтения. "
                            "Импортировать с принудительным режимом?",
                        ),
                    ):
                        run_import(True)
                    return
                messagebox_module.showerror(
                    tr("common.error", "Ошибка"),
                    tr(
                        "settings.backup.import.error",
                        "Не удалось импортировать резервную копию: {error}",
                        error=exc,
                    ),
                )

            context._run_background(
                current_task,
                on_success=on_success,
                on_error=on_error,
                busy_message=tr("settings.backup.import.busy", "Импортируем полную копию..."),
            )

        run_import(False)

    def export_backup() -> None:
        filepath = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            title=tr("settings.backup.export.title", "Экспорт полной копии"),
        )
        if not filepath:
            return

        wallets = context.repository.load_wallets()
        records = context.repository.load_all()
        mandatory_expenses = context.repository.load_mandatory_expenses()
        budgets = context.controller.get_budgets()
        debts = context.controller.get_debts()
        debt_payments = []
        for debt in debts:
            debt_payments.extend(context.controller.get_debt_history(debt.id))
        assets = context.controller.get_assets(active_only=False)
        asset_snapshots = []
        for asset in assets:
            asset_snapshots.extend(context.controller.get_asset_history(asset.id))
        goals = context.controller.get_goals()
        distribution_items, distribution_subitems_by_item = (
            context.controller.export_distribution_structure()
        )
        distribution_subitems = [
            subitem
            for item_id in sorted(distribution_subitems_by_item)
            for subitem in distribution_subitems_by_item[item_id]
        ]
        distribution_snapshots = context.controller.get_frozen_distribution_rows()
        transfers = context.repository.load_transfers()

        def task() -> None:
            from gui.exporters import export_full_backup

            export_full_backup(
                filepath,
                wallets=wallets,
                records=records,
                mandatory_expenses=mandatory_expenses,
                budgets=budgets,
                debts=debts,
                debt_payments=debt_payments,
                assets=assets,
                asset_snapshots=asset_snapshots,
                goals=goals,
                distribution_items=distribution_items,
                distribution_subitems=distribution_subitems,
                distribution_snapshots=distribution_snapshots,
                transfers=transfers,
                storage_mode="sqlite",
            )

        def on_success(_: Any) -> None:
            messagebox_module.showinfo(
                tr("common.done", "Готово"),
                tr(
                    "settings.backup.export.success",
                    "Полная копия экспортирована в {filepath}",
                    filepath=filepath,
                ),
            )
            open_in_file_manager(os.path.dirname(filepath))

        context._run_background(
            task,
            on_success=on_success,
            busy_message=tr("settings.backup.export.busy", "Экспортируем полную копию..."),
        )

    ttk.Button(
        backup_frame,
        text=tr("settings.backup.export.button", "Экспорт полной копии"),
        command=export_backup,
    ).grid(
        row=0,
        column=0,
        sticky="ew",
        padx=pad_x,
        pady=pad_y,
    )
    ttk.Button(
        backup_frame,
        text=tr("settings.backup.import.button", "Импорт полной копии"),
        command=import_backup,
    ).grid(
        row=0,
        column=1,
        sticky="ew",
        padx=pad_x,
        pady=pad_y,
    )


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
    ).grid(
        row=0,
        column=0,
        sticky="ew",
        padx=pad_x,
        pady=pad_y,
    )
