"""
Settings tab — management of wallets and mandatory expenses (CRUD, import/export), backup, audit.
"""

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
from gui.tabs.settings_support import safe_destroy, show_audit_report_dialog
from gui.ui_dialogs import messagebox_compat as messagebox
from gui.ui_helpers import (
    attach_treeview_scrollbars,
    enable_treeview_column_autosize,
    parse_numeric_input,
)
from gui.ui_theme import (
    PAD_LG,
    PAD_SM,
    PAD_XL,
    PAD_XS,
    create_card_section,
    enable_treeview_zebra,
)

logger = logging.getLogger(__name__)


class SettingsTabContext(Protocol):
    controller: Any
    repository: Any
    refresh_operation_wallet_menu: Callable[[], None] | None
    refresh_transfer_wallet_menus: Callable[[], None] | None
    refresh_wallets: Callable[[], None] | None

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
        busy_message: str = tr("app.busy.default", "Выполняется операция..."),
    ) -> None: ...


@dataclass(slots=True)
class SettingsTabBindings:
    refresh: Callable[[], None]


def build_settings_tab(
    parent: tk.Frame | ttk.Frame,
    context: SettingsTabContext,
    import_formats: dict[str, dict[str, str]],
) -> SettingsTabBindings:
    def _base_currency_code() -> str:
        getter = getattr(context.controller, "get_base_currency_code", None)
        if callable(getter):
            return str(getter() or "").strip().upper() or "KZT"
        return "KZT"

    pad_x = PAD_SM
    pad_y = PAD_XS

    parent.grid_columnconfigure(0, weight=3, uniform="settings")
    parent.grid_columnconfigure(1, weight=5, uniform="settings")
    parent.grid_rowconfigure(0, weight=1)

    left_panel = ttk.Frame(parent)
    left_panel.grid(row=0, column=0, sticky="nsew", padx=(PAD_XL, PAD_SM), pady=PAD_LG)
    left_panel.grid_columnconfigure(0, weight=1)

    right_panel = ttk.Frame(parent)
    right_panel.grid(row=0, column=1, sticky="nsew", padx=(PAD_SM, PAD_XL), pady=PAD_LG)
    right_panel.grid_rowconfigure(0, weight=1)
    right_panel.grid_columnconfigure(0, weight=1)

    wallets_card = create_card_section(left_panel, tr("settings.wallets", "Кошельки"))
    wallets_card.grid(row=0, column=0, sticky="nsew", pady=(0, PAD_LG))
    wallets_frame = wallets_card.winfo_children()[-1]
    wallets_frame.grid_columnconfigure(0, weight=1)
    wallets_frame.grid_rowconfigure(1, weight=1)

    form = ttk.Frame(wallets_frame)
    form.grid(row=0, column=0, sticky="ew", padx=pad_x, pady=pad_y)
    form.grid_columnconfigure(1, weight=1)

    ttk.Label(form, text=tr("settings.wallets.name", "Название:")).grid(row=0, column=0, sticky="w")
    wallet_name_entry = ttk.Entry(form)
    wallet_name_entry.grid(row=0, column=1, sticky="ew", pady=2)

    ttk.Label(form, text=tr("settings.wallets.currency", "Валюта:")).grid(
        row=1, column=0, sticky="w"
    )
    wallet_currency_entry = ttk.Entry(form, width=8)
    wallet_currency_entry.insert(0, _base_currency_code())
    wallet_currency_entry.grid(row=1, column=1, sticky="ew", pady=2)

    ttk.Label(form, text=tr("settings.wallets.initial_balance", "Начальный баланс:")).grid(
        row=2, column=0, sticky="w"
    )
    wallet_initial_entry = ttk.Entry(form)
    wallet_initial_entry.insert(0, "0")
    wallet_initial_entry.grid(row=2, column=1, sticky="ew", pady=2)

    wallet_allow_negative_var = tk.BooleanVar(value=False)
    ttk.Checkbutton(
        form,
        text=tr("settings.wallets.allow_negative", "Разрешить отрицательный баланс"),
        variable=wallet_allow_negative_var,
    ).grid(
        row=3,
        column=0,
        columnspan=2,
        sticky="w",
        pady=2,
    )

    list_frame = ttk.Frame(wallets_frame)
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
        wallet_tree.column(col, width=width, minwidth=minwidth, stretch=stretch, anchor=anchor)  # type: ignore
    enable_treeview_column_autosize(wallet_tree, columns=("name",), max_width=320)
    wallet_tree.grid(row=0, column=0, sticky="nsew")

    wallet_scroll, wallet_xscroll = attach_treeview_scrollbars(
        list_frame, wallet_tree, row=0, column=0, horizontal=True
    )

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

    context.refresh_wallets = refresh_wallets

    def create_wallet() -> None:
        try:
            initial_balance = float(wallet_initial_entry.get().strip() or "0")
        except ValueError:
            messagebox.showerror(
                tr("common.error", "Ошибка"),
                tr(
                    "settings.wallets.error.initial_balance",
                    "Некорректный начальный баланс кошелька.",
                ),
            )
            return

        name = ""
        try:
            name = wallet_name_entry.get().strip()
            wallet = context.controller.create_wallet(
                name=name,
                currency=(wallet_currency_entry.get() or _base_currency_code()).strip(),
                initial_balance=initial_balance,
                allow_negative=wallet_allow_negative_var.get(),
            )
            messagebox.showinfo(
                tr("common.done", "Готово"),
                tr(
                    "settings.wallets.created",
                    "Кошелек создан: [{wallet_id}] {wallet_name}",
                    wallet_id=wallet.id,
                    wallet_name=wallet.name,
                ),
            )
            wallet_name_entry.delete(0, tk.END)
            wallet_initial_entry.delete(0, tk.END)
            wallet_initial_entry.insert(0, "0")
            refresh_wallets()
        except (DomainError, ValueError, TypeError, RuntimeError) as error:
            log_ui_error(logger, "UI_SETTINGS_CREATE_WALLET_FAILED", error, name=name)
            messagebox.showerror(
                tr("common.error", "Ошибка"),
                tr(
                    "settings.wallets.error.create",
                    "Не удалось создать кошелек: {error}",
                    error=str(error),
                ),
            )

    ttk.Button(
        form,
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
            messagebox.showerror(
                tr("common.error", "Ошибка"),
                tr("settings.wallets.error.select_delete", "Выберите кошелек для удаления."),
            )
            return
        try:
            values = wallet_tree.item(selection[0], "values")
            wallet_id = int(values[0])
        except (TypeError, ValueError, IndexError):
            messagebox.showerror(
                tr("common.error", "Ошибка"),
                tr(
                    "settings.wallets.error.parse_id",
                    "Не удалось определить идентификатор выбранного кошелька.",
                ),
            )
            return

        try:
            context.controller.soft_delete_wallet(wallet_id)
            messagebox.showinfo(
                tr("common.done", "Готово"),
                tr("settings.wallets.deleted", "Кошелек деактивирован."),
            )
            refresh_wallets()
        except (DomainError, ValueError, TypeError, RuntimeError) as error:
            log_ui_error(logger, "UI_SETTINGS_DELETE_WALLET_FAILED", error, wallet_id=wallet_id)
            messagebox.showerror(tr("common.error", "Ошибка"), str(error))

    wallet_actions = ttk.Frame(wallets_frame)
    wallet_actions.grid(row=2, column=0, sticky="ew", padx=pad_x, pady=pad_y)
    wallet_actions.grid_columnconfigure(0, weight=1)
    wallet_actions.grid_columnconfigure(1, weight=1)

    ttk.Button(
        wallet_actions,
        text=tr("settings.wallets.delete", "Удалить кошелек"),
        command=delete_wallet,
    ).grid(
        row=0,
        column=0,
        sticky="ew",
        padx=(0, 4),
    )
    ttk.Button(
        wallet_actions,
        text=tr("common.refresh", "Обновить"),
        command=refresh_wallets,
    ).grid(
        row=0,
        column=1,
        sticky="ew",
        padx=(4, 0),
    )

    refresh_wallets()

    mand_card = create_card_section(right_panel, tr("settings.mandatory", "Обязательные расходы"))
    mand_card.grid(row=0, column=0, sticky="nsew")
    mand_frame = mand_card.winfo_children()[-1]
    mand_frame.grid_rowconfigure(0, weight=1)
    mand_frame.grid_columnconfigure(0, weight=1)

    mand_list_frame = ttk.Frame(mand_frame)
    mand_list_frame.grid(row=0, column=0, columnspan=2, sticky="nsew", padx=pad_x, pady=pad_y)
    mand_list_frame.grid_rowconfigure(0, weight=1)
    mand_list_frame.grid_columnconfigure(0, weight=1)

    mand_tree = ttk.Treeview(
        mand_list_frame,
        show="headings",
        selectmode="browse",
        columns=(
            "index",
            "amount",
            "currency",
            "kzt",
            "category",
            "description",
            "period",
            "date",
            "autopay",
        ),
        height=10,
    )
    enable_treeview_zebra(mand_tree)
    for col, text, width, minwidth, stretch, anchor in (
        ("index", "#", 40, 40, False, "e"),
        ("amount", tr("settings.mandatory.amount", "Сумма"), 90, 90, False, "e"),
        ("currency", tr("settings.mandatory.currency_short", "Вал."), 60, 60, False, "center"),
        ("kzt", "KZT", 90, 90, False, "e"),
        ("category", tr("settings.mandatory.category", "Категория"), 120, 120, False, "w"),
        ("description", tr("settings.mandatory.description", "Описание"), 200, 160, True, "w"),
        ("period", tr("settings.mandatory.period", "Период"), 90, 80, False, "w"),
        ("date", tr("settings.mandatory.date", "Дата"), 100, 100, False, "w"),
        ("autopay", tr("settings.mandatory.autopay", "Автоплатеж"), 120, 100, False, "center"),
    ):
        mand_tree.heading(col, text=text)
        mand_tree.column(col, width=width, minwidth=minwidth, stretch=stretch, anchor=anchor)  # type: ignore[arg-type]
    enable_treeview_column_autosize(
        mand_tree,
        columns=("category", "description"),
        max_width=360,
    )
    mand_tree.grid(row=0, column=0, sticky="nsew")

    mand_scroll, mand_xscroll = attach_treeview_scrollbars(
        mand_list_frame, mand_tree, row=0, column=0, horizontal=True
    )

    def _mandatory_scroll_units(delta: int, *, multiplier: int = 12) -> int:
        if delta == 0:
            return 0
        base_units = max(1, abs(int(delta)) // 120)
        return base_units * multiplier

    def _scroll_mandatory_horizontally(direction: int, units: int) -> str:
        mand_tree.xview_scroll(direction * units, "units")
        return "break"

    def _on_mandatory_shift_mousewheel(event: tk.Event) -> str:
        delta = int(getattr(event, "delta", 0))
        units = _mandatory_scroll_units(delta)
        if units <= 0:
            return "break"
        direction = -1 if delta > 0 else 1
        return _scroll_mandatory_horizontally(direction, units)

    def _on_mandatory_shift_button4(_event: tk.Event) -> str:
        return _scroll_mandatory_horizontally(-1, 3)

    def _on_mandatory_shift_button5(_event: tk.Event) -> str:
        return _scroll_mandatory_horizontally(1, 3)

    for widget in (mand_tree, mand_xscroll):
        if widget is not None:
            widget.bind("<Shift-MouseWheel>", _on_mandatory_shift_mousewheel, add="+")
            widget.bind("<Shift-Button-4>", _on_mandatory_shift_button4, add="+")
            widget.bind("<Shift-Button-5>", _on_mandatory_shift_button5, add="+")

    def refresh_mandatory() -> None:
        mand_tree.heading("kzt", text=context.controller.get_display_currency_code())
        for iid in mand_tree.get_children():
            mand_tree.delete(iid)
        expenses = context.controller.load_mandatory_expenses()
        for idx, expense in enumerate(expenses):
            date_value = (
                expense.date.isoformat()
                if getattr(expense.date, "isoformat", None) is not None
                else str(expense.date or "")
            )
            values = (
                str(idx),
                f"{float(expense.amount_original or 0.0):,.2f}",
                str(expense.currency or _base_currency_code()).upper(),
                context.controller.format_display_amount(float(expense.amount_base or 0.0)),
                str(expense.category or ""),
                str(expense.description or ""),
                str(expense.period or ""),
                str(date_value),
                "✓" if bool(expense.auto_pay) else "",
            )
            mand_tree.insert("", "end", iid=str(idx), values=values)

    current_panel: dict[str, tk.Frame | ttk.Frame | None] = {
        "add": None,
        "report": None,
        "edit": None,
    }

    def close_inline_panels() -> None:
        for key in ("add", "report", "edit"):
            panel = current_panel[key]
            if panel is not None:
                safe_destroy(panel)
                current_panel[key] = None

    def _configure_inline_panel_grid(panel: ttk.Frame) -> None:
        panel.grid_columnconfigure(0, minsize=280)
        panel.grid_columnconfigure(1, weight=1, minsize=320)

    def add_mandatory_inline() -> None:
        close_inline_panels()

        add_panel = ttk.Frame(mand_frame, style="InlinePanel.TFrame", padding=(PAD_SM, PAD_XS))
        add_panel.grid(row=2, column=0, columnspan=2, pady=PAD_SM, sticky="ew")
        _configure_inline_panel_grid(add_panel)
        current_panel["add"] = add_panel

        ttk.Label(add_panel, text=tr("settings.mandatory.field.amount", "Сумма:")).grid(
            row=0, column=0, sticky="w"
        )
        amount_entry = ttk.Entry(add_panel)
        amount_entry.grid(row=0, column=1, sticky="ew", pady=2)

        ttk.Label(
            add_panel,
            text=tr(
                "settings.mandatory.field.currency_default",
                "Валюта (по умолчанию валюта базы):",
            ),
        ).grid(row=1, column=0, sticky="w")
        currency_entry = ttk.Entry(add_panel)
        currency_entry.insert(0, _base_currency_code())
        currency_entry.grid(row=1, column=1, sticky="ew", pady=2)

        ttk.Label(add_panel, text=tr("common.wallet", "Кошелек:")).grid(row=2, column=0, sticky="w")
        mandatory_wallet_var = tk.StringVar(value="")
        mandatory_wallet_menu = ttk.Combobox(
            add_panel,
            textvariable=mandatory_wallet_var,
            values=[],
            state="readonly",
        )
        mandatory_wallet_menu.grid(row=2, column=1, sticky="ew")
        mandatory_wallet_map: dict[str, int] = {
            f"[{wallet.id}] {wallet.name} ({wallet.currency})": wallet.id
            for wallet in context.controller.load_active_wallets()
        }
        wallet_labels = list(mandatory_wallet_map.keys()) or [""]
        mandatory_wallet_menu["values"] = wallet_labels
        mandatory_wallet_var.set(wallet_labels[0])

        ttk.Label(
            add_panel,
            text=tr(
                "settings.mandatory.field.category_default", "Категория (по умолчанию Mandatory):"
            ),
        ).grid(row=3, column=0, sticky="w")
        category_entry = ttk.Entry(add_panel)
        category_entry.insert(0, "Mandatory")
        category_entry.grid(row=3, column=1, sticky="ew", pady=2)

        ttk.Label(add_panel, text=tr("common.description", "Описание:")).grid(
            row=4, column=0, sticky="w"
        )
        description_entry = ttk.Entry(add_panel)
        description_entry.grid(row=4, column=1, sticky="ew", pady=2)

        ttk.Label(add_panel, text=tr("common.period", "Период:")).grid(row=5, column=0, sticky="w")
        period_var = tk.StringVar(value="monthly")
        period_combo = ttk.Combobox(
            add_panel,
            textvariable=period_var,
            values=["daily", "weekly", "monthly", "yearly"],
            state="readonly",
        )
        period_combo.grid(row=5, column=1, sticky="ew", pady=2)

        ttk.Label(
            add_panel,
            text=tr("settings.mandatory.field.date_optional", "Дата (YYYY-MM-DD, необязательно):"),
        ).grid(row=6, column=0, sticky="w")
        date_entry = ttk.Entry(add_panel)
        date_entry.grid(row=6, column=1, sticky="ew", pady=2)

        def save() -> None:
            wallet_id = None
            try:
                amount = float(amount_entry.get())
                description = description_entry.get()
                if not description:
                    messagebox.showerror(
                        tr("common.error", "Ошибка"),
                        tr(
                            "settings.mandatory.error.description_required", "Описание обязательно."
                        ),
                    )
                    return
                date_val = date_entry.get().strip()
                if date_val:
                    try:
                        from domain.validation import parse_ymd

                        parse_ymd(date_val)
                    except ValueError:
                        messagebox.showerror(
                            tr("common.error", "Ошибка"),
                            tr(
                                "settings.mandatory.error.invalid_date",
                                "Некорректная дата. Используйте YYYY-MM-DD.",
                            ),
                        )
                        return
                wallet_id = mandatory_wallet_map.get(mandatory_wallet_var.get())
                if wallet_id is None:
                    messagebox.showerror(
                        tr("common.error", "Ошибка"),
                        tr("settings.mandatory.error.wallet_required", "Кошелек обязателен."),
                    )
                    return
                context.controller.create_mandatory_expense(
                    amount=amount,
                    currency=(currency_entry.get() or _base_currency_code()).strip(),
                    wallet_id=wallet_id,
                    category=(category_entry.get() or "Mandatory").strip(),
                    description=description,
                    period=period_var.get(),
                    date=date_val,
                )
                messagebox.showinfo(
                    tr("common.done", "Готово"),
                    tr("settings.mandatory.added", "Обязательный расход добавлен."),
                )
                safe_destroy(add_panel)
                current_panel["add"] = None
                context._refresh_charts()
                refresh_mandatory()
                context._refresh_budgets()
            except (DomainError, ValueError, TypeError, RuntimeError) as error:
                log_ui_error(
                    logger,
                    "UI_SETTINGS_MANDATORY_CREATE_FAILED",
                    error,
                    wallet_id=wallet_id,
                )
                messagebox.showerror(
                    tr("common.error", "Ошибка"),
                    tr(
                        "settings.mandatory.error.add_failed",
                        "Не удалось добавить расход: {error}",
                        error=error,
                    ),
                )

        def cancel() -> None:
            try:
                safe_destroy(add_panel)
            finally:
                current_panel["add"] = None

        add_buttons = ttk.Frame(add_panel, style="InlinePanel.TFrame")
        add_buttons.grid(row=7, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        add_buttons.grid_columnconfigure(0, weight=1)
        add_buttons.grid_columnconfigure(1, weight=1)
        ttk.Button(
            add_buttons, text=tr("common.save", "Сохранить"), style="Primary.TButton", command=save
        ).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ttk.Button(add_buttons, text=tr("common.cancel", "Отмена"), command=cancel).grid(
            row=0, column=1, sticky="ew", padx=(6, 0)
        )

    def edit_mandatory_inline() -> None:
        selection = mand_tree.selection()
        if not selection:
            messagebox.showerror(
                tr("common.error", "Ошибка"),
                tr(
                    "settings.mandatory.error.select_edit",
                    "Выберите обязательный расход для редактирования.",
                ),
            )
            return
        try:
            index = int(selection[0])
        except (TypeError, ValueError):
            messagebox.showerror(
                tr("common.error", "Ошибка"), tr("common.invalid_selection", "Некорректный выбор.")
            )
            return
        expenses = context.controller.load_mandatory_expenses()
        if not (0 <= index < len(expenses)):
            return
        expense = expenses[index]

        close_inline_panels()

        edit_panel = ttk.Frame(mand_frame, style="InlinePanel.TFrame", padding=(8, 6))
        edit_panel.grid(row=2, column=0, columnspan=2, pady=6, sticky="ew")
        current_panel["edit"] = edit_panel
        _configure_inline_panel_grid(edit_panel)

        ttk.Label(
            edit_panel,
            text=tr("settings.mandatory.field.amount_base", "Сумма в валюте базы:"),
        ).grid(row=0, column=0, sticky="w")
        amount_base_entry = ttk.Entry(edit_panel)
        amount_base_entry.insert(0, str(expense.amount_base))
        amount_base_entry.grid(row=0, column=1, sticky="ew", pady=2)

        ttk.Label(edit_panel, text=tr("common.wallet", "Кошелек:")).grid(
            row=1, column=0, sticky="w"
        )
        edit_wallet_var = tk.StringVar(value="")
        edit_wallet_menu = ttk.Combobox(
            edit_panel,
            textvariable=edit_wallet_var,
            values=[],
            state="readonly",
        )
        edit_wallet_menu.grid(row=1, column=1, sticky="ew")
        edit_wallet_map: dict[str, int] = {
            f"[{wallet.id}] {wallet.name} ({wallet.currency})": wallet.id
            for wallet in context.controller.load_active_wallets()
        }
        edit_wallet_labels = list(edit_wallet_map.keys()) or [""]
        edit_wallet_menu["values"] = edit_wallet_labels
        current_wallet_label = next(
            (label for label, wid in edit_wallet_map.items() if int(wid) == int(expense.wallet_id)),
            edit_wallet_labels[0],
        )
        edit_wallet_var.set(current_wallet_label)

        ttk.Label(edit_panel, text=tr("common.period", "Период:")).grid(row=2, column=0, sticky="w")
        edit_period_var = tk.StringVar(value=str(expense.period or "monthly"))
        edit_period_combo = ttk.Combobox(
            edit_panel,
            textvariable=edit_period_var,
            values=["daily", "weekly", "monthly", "yearly"],
            state="readonly",
        )
        edit_period_combo.grid(row=2, column=1, sticky="ew")

        ttk.Label(
            edit_panel,
            text=tr("settings.mandatory.field.date_optional", "Дата (YYYY-MM-DD, необязательно):"),
        ).grid(row=3, column=0, sticky="w")
        date_entry = ttk.Entry(edit_panel)
        date_entry.insert(
            0,
            expense.date.isoformat()
            if hasattr(expense.date, "isoformat")
            else str(expense.date or ""),
        )
        date_entry.grid(row=3, column=1, sticky="ew", pady=2)

        def save_edit() -> None:
            expense_id = int(expense.id)
            raw_amount = amount_base_entry.get().strip()
            current_amount = str(expense.amount_base)
            if raw_amount != current_amount:
                try:
                    context.controller.update_mandatory_expense_amount_base(
                        expense_id, parse_numeric_input(raw_amount)
                    )
                except ValueError as error:
                    messagebox.showerror(
                        tr("settings.mandatory.error.amount_title", "Ошибка суммы"), str(error)
                    )
                    return

            new_wallet_id = edit_wallet_map.get(edit_wallet_var.get())
            if new_wallet_id is None:
                messagebox.showerror(
                    tr("common.error", "Ошибка"),
                    tr("settings.mandatory.error.wallet_required", "Кошелек обязателен."),
                )
                return
            if int(new_wallet_id) != int(expense.wallet_id):
                try:
                    context.controller.update_mandatory_expense_wallet_id(
                        expense_id, int(new_wallet_id)
                    )
                except ValueError as error:
                    messagebox.showerror(
                        tr("settings.mandatory.error.wallet_title", "Ошибка кошелька"), str(error)
                    )
                    return

            new_period = str(edit_period_var.get() or "").strip().lower()
            if new_period and str(new_period) != str(expense.period):
                try:
                    context.controller.update_mandatory_expense_period(expense_id, new_period)
                except ValueError as error:
                    messagebox.showerror(
                        tr("settings.mandatory.error.period_title", "Ошибка периода"), str(error)
                    )
                    return

            current_date = (
                expense.date.isoformat()
                if hasattr(expense.date, "isoformat")
                else str(expense.date or "")
            )
            new_date = date_entry.get().strip()
            if new_date != current_date:
                try:
                    context.controller.update_mandatory_expense_date(expense_id, new_date)
                except ValueError as error:
                    messagebox.showerror(
                        tr("settings.mandatory.error.date_title", "Ошибка даты"), str(error)
                    )
                    return

            safe_destroy(edit_panel)
            current_panel["edit"] = None
            refresh_mandatory()
            context._refresh_charts()
            context._refresh_budgets()
            messagebox.showinfo(
                tr("common.done", "Готово"),
                tr("settings.mandatory.updated", "Обязательный расход обновлен."),
            )

        def cancel_edit() -> None:
            try:
                safe_destroy(edit_panel)
            finally:
                current_panel["edit"] = None

        edit_buttons = ttk.Frame(edit_panel, style="InlinePanel.TFrame")
        edit_buttons.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        edit_buttons.grid_columnconfigure(0, weight=1)
        edit_buttons.grid_columnconfigure(1, weight=1)
        ttk.Button(
            edit_buttons,
            text=tr("common.save", "Сохранить"),
            style="Primary.TButton",
            command=save_edit,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ttk.Button(edit_buttons, text=tr("common.cancel", "Отмена"), command=cancel_edit).grid(
            row=0, column=1, sticky="ew", padx=(6, 0)
        )

    def add_to_records_inline() -> None:
        selection = mand_tree.selection()
        if not selection:
            selection = mand_tree.selection()
            messagebox.showerror(
                tr("common.error", "Ошибка"),
                tr(
                    "settings.mandatory.error.select_add_to_records",
                    "Выберите обязательный расход для добавления в записи.",
                ),
            )
            return
        close_inline_panels()

        add_to_report_panel = ttk.Frame(mand_frame, style="InlinePanel.TFrame", padding=(8, 6))
        add_to_report_panel.grid(row=2, column=0, columnspan=2, pady=6, sticky="ew")
        _configure_inline_panel_grid(add_to_report_panel)
        current_panel["report"] = add_to_report_panel

        ttk.Label(
            add_to_report_panel,
            text=tr("settings.mandatory.field.date_required", "Дата (YYYY-MM-DD):"),
        ).grid(row=0, column=0, sticky="w")
        date_entry = ttk.Entry(add_to_report_panel)
        date_entry.grid(row=0, column=1, sticky="ew", pady=2)

        ttk.Label(add_to_report_panel, text=tr("common.wallet", "Кошелек:")).grid(
            row=1, column=0, sticky="w"
        )
        mandatory_wallet_var = tk.StringVar(value="")
        mandatory_wallet_menu = ttk.Combobox(
            add_to_report_panel,
            textvariable=mandatory_wallet_var,
            values=[],
            state="readonly",
        )
        mandatory_wallet_menu.grid(row=1, column=1, sticky="ew")

        mandatory_wallet_map: dict[str, int] = {
            f"[{wallet.id}] {wallet.name} ({wallet.currency})": wallet.id
            for wallet in context.controller.load_active_wallets()
        }
        wallet_labels = list(mandatory_wallet_map.keys()) or [""]
        mandatory_wallet_menu["values"] = wallet_labels
        mandatory_wallet_var.set(wallet_labels[0])

        selection = mand_tree.selection()
        if selection:
            try:
                index = int(selection[0])
            except (TypeError, ValueError):
                index = -1
        else:
            index = -1

        def save() -> None:
            try:
                from domain.validation import ensure_not_future, parse_ymd

                date_value = date_entry.get()
                entered_date = parse_ymd(date_value)
                ensure_not_future(entered_date)
                wallet_id = mandatory_wallet_map.get(mandatory_wallet_var.get())
                if wallet_id is None:
                    messagebox.showerror(
                        tr("common.error", "Ошибка"),
                        tr("settings.mandatory.error.wallet_required", "Кошелек обязателен."),
                    )
                    return

                context.controller.add_mandatory_to_report(index, date_value, wallet_id)
                messagebox.showinfo(
                    tr("common.done", "Готово"),
                    tr(
                        "settings.mandatory.added_to_records",
                        "Обязательный расход добавлен в записи за {date}.",
                        date=date_value,
                    ),
                )
                safe_destroy(add_to_report_panel)
                current_panel["report"] = None
                refresh_mandatory()
                refresh_wallets()
                context._refresh_list()
                context._refresh_charts()
                context._refresh_budgets()
                context._refresh_all()
            except ValueError as error:
                messagebox.showerror(
                    tr("common.error", "Ошибка"),
                    tr(
                        "settings.mandatory.error.invalid_date_with_hint",
                        "Некорректная дата: {error}. Используйте YYYY-MM-DD.",
                        error=error,
                    ),
                )

        def cancel() -> None:
            try:
                safe_destroy(add_to_report_panel)
            finally:
                current_panel["report"] = None

        report_buttons = ttk.Frame(add_to_report_panel, style="InlinePanel.TFrame")
        report_buttons.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        report_buttons.grid_columnconfigure(0, weight=1)
        report_buttons.grid_columnconfigure(1, weight=1)
        ttk.Button(
            report_buttons,
            text=tr("common.save", "Сохранить"),
            style="Primary.TButton",
            command=save,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ttk.Button(report_buttons, text=tr("common.cancel", "Отмена"), command=cancel).grid(
            row=0, column=1, sticky="ew", padx=(6, 0)
        )

    def delete_mandatory() -> None:
        selection = mand_tree.selection()
        if not selection:
            messagebox.showerror(
                tr("common.error", "Ошибка"),
                tr(
                    "settings.mandatory.error.select_delete",
                    "Выберите обязательный расход для удаления.",
                ),
            )
            return
        try:
            index = int(selection[0])
        except (TypeError, ValueError):
            messagebox.showerror(
                tr("common.error", "Ошибка"), tr("common.invalid_selection", "Некорректный выбор.")
            )
            return
        if context.controller.delete_mandatory_expense(index):
            messagebox.showinfo(
                tr("common.done", "Готово"),
                tr("settings.mandatory.deleted", "Обязательный расход удален."),
            )
            refresh_mandatory()
        else:
            messagebox.showerror(
                tr("common.error", "Ошибка"),
                tr(
                    "settings.mandatory.error.delete_failed",
                    "Не удалось удалить обязательный расход.",
                ),
            )

    def delete_all_mandatory() -> None:
        if not messagebox.askyesno(
            tr("common.confirm", "Подтверждение"),
            tr(
                "settings.mandatory.confirm_delete_all",
                "Удалить ВСЕ обязательные расходы? Это действие нельзя отменить.",
            ),
        ):
            return
        context.controller.delete_all_mandatory_expenses()
        messagebox.showinfo(
            tr("common.done", "Готово"),
            tr("settings.mandatory.deleted_all", "Все обязательные расходы удалены."),
        )
        refresh_mandatory()

    actions = ttk.Frame(mand_frame)
    actions.grid(row=1, column=0, columnspan=2, sticky="ew", padx=pad_x, pady=(0, pad_y))
    for idx in range(5):
        actions.grid_columnconfigure(idx, weight=1)

    format_var = tk.StringVar(value="CSV")

    ttk.Button(actions, text=tr("common.create", "Создать"), command=add_mandatory_inline).grid(
        row=0, column=0, sticky="ew", padx=(0, 6), pady=(0, 6)
    )
    ttk.Button(
        actions, text=tr("common.edit", "Редактировать"), command=edit_mandatory_inline
    ).grid(row=0, column=1, sticky="ew", padx=6, pady=(0, 6))
    ttk.Button(
        actions,
        text=tr("settings.mandatory.add_to_records", "Добавить в записи"),
        command=add_to_records_inline,
    ).grid(row=0, column=2, sticky="ew", padx=6, pady=(0, 6))
    ttk.Button(actions, text=tr("common.delete", "Удалить"), command=delete_mandatory).grid(
        row=0, column=3, sticky="ew", padx=6, pady=(0, 6)
    )
    ttk.Button(
        actions,
        text=tr("settings.mandatory.delete_all", "Удалить все"),
        command=delete_all_mandatory,
    ).grid(row=0, column=4, sticky="ew", padx=(6, 0), pady=(0, 6))
    ttk.Button(actions, text=tr("common.refresh", "Обновить"), command=refresh_mandatory).grid(
        row=1, column=0, sticky="ew", padx=(0, 6)
    )
    ttk.Combobox(
        actions,
        textvariable=format_var,
        values=["CSV", "XLSX"],
        state="readonly",
    ).grid(row=1, column=1, sticky="ew", padx=6)

    def import_mand() -> None:
        fmt = format_var.get()
        cfg = import_formats.get(fmt)
        if not cfg:
            messagebox.showerror(
                tr("common.error", "Ошибка"),
                tr("common.unsupported_format", "Неподдерживаемый формат: {fmt}", fmt=fmt),
            )
            return

        filepath = filedialog.askopenfilename(
            defaultextension=cfg["ext"],
            filetypes=[(f"{cfg['desc']} files", f"*{cfg['ext']}"), ("All files", "*.*")],
            title=tr(
                "settings.mandatory.import.select_file",
                "Выберите файл {desc} для импорта обязательных расходов",
                desc=cfg["desc"],
            ),
        )
        if not filepath:
            return

        if not messagebox.askyesno(
            tr("common.confirm", "Подтверждение"),
            tr(
                "settings.mandatory.import.confirm",
                "Это заменит все существующие обязательные расходы данными из:\n{filepath}\n"
                "\nПродолжить?",
                filepath=filepath,
            ),
        ):
            return

        def task() -> ImportResult:
            return context.controller.import_mandatory(fmt, filepath)

        def on_success(result: ImportResult) -> None:
            details = ""
            if result.skipped:
                details = f"\nSkipped: {result.skipped} rows.\nFirst errors:\n- " + "\n- ".join(
                    result.errors[:5]
                )

            messagebox.showinfo(
                tr("common.done", "Готово"),
                tr(
                    "settings.mandatory.import.success",
                    "Успешно импортировано {count} обязательных расходов из файла {desc}."
                    "\nВсе существующие обязательные расходы были заменены.",
                    count=result.imported,
                    desc=cfg["desc"],
                )
                + details,
            )
            refresh_mandatory()

        def on_error(exc: BaseException) -> None:
            if isinstance(exc, FileNotFoundError):
                messagebox.showerror(
                    tr("common.error", "Ошибка"),
                    tr("common.file_not_found", "Файл не найден: {filepath}", filepath=filepath),
                )
                return
            messagebox.showerror(
                tr("common.error", "Ошибка"),
                tr(
                    "settings.mandatory.import.error",
                    "Не удалось импортировать {fmt}: {error}",
                    fmt=fmt,
                    error=exc,
                ),
            )

        context._run_background(
            task,
            on_success=on_success,
            on_error=on_error,
            busy_message=tr(
                "settings.mandatory.import.busy",
                "Импортируем обязательные расходы из {desc}...",
                desc=cfg["desc"],
            ),
        )

    def export_mand() -> None:
        fmt = format_var.get()
        expenses = context.controller.load_mandatory_expenses()
        if not expenses:
            messagebox.showinfo(
                tr("settings.mandatory.export.empty_title", "Нет расходов"),
                tr("settings.mandatory.export.empty", "Нет обязательных расходов для экспорта."),
            )
            return

        filepath = filedialog.asksaveasfilename(
            defaultextension=f".{fmt.lower()}",
            title=tr("settings.mandatory.export.save", "Сохранить обязательные расходы"),
        )
        if not filepath:
            return

        def task() -> None:
            from gui.exporters import export_mandatory_expenses

            export_mandatory_expenses(expenses, filepath, fmt.lower())

        def on_success(_: Any) -> None:
            messagebox.showinfo(
                tr("common.done", "Готово"),
                tr(
                    "settings.mandatory.export.success",
                    "Обязательные расходы экспортированы в {filepath}",
                    filepath=filepath,
                ),
            )
            open_in_file_manager(os.path.dirname(filepath))

        context._run_background(
            task,
            on_success=on_success,
            busy_message=tr(
                "settings.mandatory.export.busy",
                "Экспортируем обязательные расходы в {fmt}...",
                fmt=fmt,
            ),
        )

    ttk.Button(actions, text=tr("operations.import", "Импорт"), command=import_mand).grid(
        row=1, column=2, sticky="ew", padx=6
    )
    ttk.Button(actions, text=tr("operations.export", "Экспорт"), command=export_mand).grid(
        row=1, column=3, sticky="ew", padx=6
    )

    backup_card = create_card_section(left_panel, tr("settings.backup", "Резервная копия (JSON)"))
    backup_card.grid(row=2, column=0, sticky="ew")
    backup_frame = backup_card.winfo_children()[-1]
    backup_frame.grid_columnconfigure(0, weight=1)
    backup_frame.grid_columnconfigure(1, weight=1)

    def import_backup() -> None:
        filepath = filedialog.askopenfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            title=tr("settings.backup.import.title", "Импорт полной копии"),
        )
        if not filepath:
            return

        if not messagebox.askyesno(
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
            messagebox.showinfo(
                tr("common.done", "Готово"),
                tr(
                    "settings.backup.import.success",
                    "Резервная копия импортирована. Импортировано сущностей: {count}.{details}",
                    count=result.imported,
                    details=details,
                ),
            )
            refresh_mandatory()
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
                    if messagebox.askyesno(
                        tr("settings.backup.readonly.title", "Снимок только для чтения"),
                        tr(
                            "settings.backup.readonly.confirm",
                            "Резервная копия доступна только для чтения. "
                            "Импортировать с принудительным режимом?",
                        ),
                    ):
                        run_import(True)
                    return
                messagebox.showerror(
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
            messagebox.showinfo(
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

    audit_card = create_card_section(left_panel, tr("settings.audit", "Финансовый аудит"))
    audit_card.grid(row=3, column=0, sticky="ew", pady=(PAD_LG, 0))
    audit_frame = audit_card.winfo_children()[-1]
    audit_frame.grid_columnconfigure(0, weight=1)

    def _on_run_audit() -> None:
        try:
            report = context.controller.run_audit()
            show_audit_report_dialog(report, parent)
        except (DomainError, ValueError, TypeError, RuntimeError) as error:
            log_ui_error(logger, "UI_SETTINGS_AUDIT_FAILED", error)
            messagebox.showerror(tr("settings.audit.error_title", "Ошибка аудита"), str(error))

    ttk.Button(
        audit_frame, text=tr("settings.audit.run", "Запустить аудит"), command=_on_run_audit
    ).grid(
        row=0,
        column=0,
        sticky="ew",
        padx=pad_x,
        pady=pad_y,
    )

    refresh_mandatory()
    return SettingsTabBindings(refresh=refresh_mandatory)
