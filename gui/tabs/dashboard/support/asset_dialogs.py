"""Asset editor and manager dialogs for the dashboard tab."""

from __future__ import annotations

import logging
import tkinter as tk
from collections.abc import Callable
from datetime import date
from tkinter import ttk

from domain.asset import Asset
from domain.errors import DomainError
from gui.combobox_compat import enable_wayland_combobox_support
from gui.i18n import tr
from gui.logging_utils import log_ui_error
from gui.ui_helpers import (
    ask_confirm,
    center_dialog,
    enable_treeview_column_autosize,
    show_error,
    show_info,
)

from ..core.contracts import DashboardTabContext
from .actions import (
    _asset_actions_state,
    _asset_form_error,
    _prepare_asset_payload,
    base_currency_code,
    set_button_enabled,
)

logger = logging.getLogger(__name__)


def show_asset_editor_dialog(
    parent: tk.Misc,
    *,
    context: DashboardTabContext,
    initial_asset: Asset | None,
    on_saved: Callable[[], None],
) -> None:
    dialog = tk.Toplevel(parent)
    dialog.withdraw()
    dialog.title(
        tr("dashboard.asset.edit_title", "Редактирование актива")
        if initial_asset is not None
        else tr("dashboard.asset.create_title", "Создание актива")
    )
    dialog.transient(parent.winfo_toplevel())
    dialog.grid_columnconfigure(0, weight=1)
    dialog.grid_rowconfigure(0, weight=1)

    content = ttk.Frame(dialog, padding=12)
    content.grid(row=0, column=0, sticky="nsew")
    for column in (1, 3):
        content.grid_columnconfigure(column, weight=1)

    categories = ["bank", "crypto", "cash", "other"]
    name_var = tk.StringVar(value="" if initial_asset is None else str(initial_asset.name))
    category_var = tk.StringVar(
        value="bank" if initial_asset is None else str(initial_asset.category.value)
    )
    currency_var = tk.StringVar(
        value=(
            base_currency_code(context.controller)
            if initial_asset is None
            else str(initial_asset.currency)
        )
    )
    created_at_var = tk.StringVar(
        value=date.today().isoformat() if initial_asset is None else str(initial_asset.created_at)
    )
    description_var = tk.StringVar(
        value="" if initial_asset is None else str(initial_asset.description or "")
    )
    currency_warning_var = tk.StringVar(value="")

    ttk.Label(
        content,
        text=(
            tr("dashboard.asset.edit_title", "Редактирование актива")
            if initial_asset is not None
            else tr("dashboard.asset.create_title", "Создание актива")
        ),
        font=("Segoe UI", 11, "bold"),
    ).grid(row=0, column=0, columnspan=4, sticky="w")

    ttk.Label(content, text=tr("common.name", "Название:")).grid(
        row=1, column=0, sticky="w", pady=(10, 0)
    )
    name_entry = ttk.Entry(content, textvariable=name_var, width=28)
    name_entry.grid(row=2, column=0, columnspan=2, sticky="ew", padx=(0, 10))

    ttk.Label(content, text=tr("common.category", "Категория:")).grid(
        row=1, column=2, sticky="w", pady=(10, 0)
    )
    category_combo = ttk.Combobox(
        content,
        textvariable=category_var,
        values=categories,
        state="readonly",
        width=12,
    )
    category_combo.grid(row=2, column=2, sticky="ew", padx=(0, 10))
    enable_wayland_combobox_support(category_combo, bind_down=False)

    ttk.Label(content, text=tr("common.currency", "Валюта:")).grid(
        row=1, column=3, sticky="w", pady=(10, 0)
    )
    currency_entry = ttk.Entry(content, textvariable=currency_var, width=8)
    currency_entry.grid(row=2, column=3, sticky="ew")

    ttk.Label(content, text=tr("common.created_at", "Дата создания:")).grid(
        row=3, column=0, sticky="w", pady=(10, 0)
    )
    created_at_entry = ttk.Entry(content, textvariable=created_at_var, width=16)
    created_at_entry.grid(row=4, column=0, sticky="ew", padx=(0, 10))
    if initial_asset is not None:
        created_at_entry.state(["readonly"])

    ttk.Label(content, text=tr("common.description", "Описание:")).grid(
        row=3, column=1, columnspan=3, sticky="w", pady=(10, 0)
    )
    description_entry = ttk.Entry(content, textvariable=description_var)
    description_entry.grid(row=4, column=1, columnspan=3, sticky="ew")

    ttk.Label(
        content,
        text=(
            tr("dashboard.asset.created_hint", "Дата создания в формате ГГГГ-ММ-ДД.")
            if initial_asset is None
            else tr(
                "dashboard.asset.created_readonly",
                "Для существующего актива дата создания не редактируется.",
            )
        ),
        foreground="#6b7280",
    ).grid(row=5, column=0, columnspan=4, sticky="w", pady=(8, 0))
    currency_warning = ttk.Label(content, textvariable=currency_warning_var, foreground="#b45309")
    currency_warning.grid(row=6, column=0, columnspan=4, sticky="w", pady=(8, 0))
    form_status = ttk.Label(content, foreground="#b45309")
    form_status.grid(row=7, column=0, columnspan=4, sticky="w", pady=(4, 0))

    buttons = ttk.Frame(content)
    buttons.grid(row=8, column=0, columnspan=4, sticky="e", pady=(12, 0))

    def _close() -> None:
        dialog.destroy()

    def _validate_form(*_args) -> None:
        created_at_value = (
            str(initial_asset.created_at) if initial_asset is not None else created_at_var.get()
        )
        error = _asset_form_error(
            name=name_var.get(),
            category=category_var.get(),
            currency=currency_var.get(),
            created_at=created_at_value,
            description=description_var.get(),
        )
        form_status.config(text=error or "")
        if (
            initial_asset is not None
            and str(currency_var.get()).strip().upper()
            != str(initial_asset.currency).strip().upper()
        ):
            currency_warning_var.set(
                tr(
                    "dashboard.asset.currency_warning",
                    "При смене валюты актива нужно сохранить новый снимок в новой валюте.",
                )
            )
        else:
            currency_warning_var.set("")
        set_button_enabled(save_button, error is None)

    def _save() -> None:
        try:
            payload = _prepare_asset_payload(
                name=name_var.get(),
                category=category_var.get(),
                currency=currency_var.get(),
                created_at=(
                    str(initial_asset.created_at)
                    if initial_asset is not None
                    else created_at_var.get()
                ),
                description=description_var.get(),
            )
            if initial_asset is None:
                context.controller.create_asset(**payload)
            else:
                context.controller.update_asset(initial_asset.id, **payload)
        except (DomainError, ValueError, TypeError, RuntimeError) as error:
            log_ui_error(
                logger,
                "UI_DASH_ASSET_SAVE_FAILED",
                error,
                asset_id=getattr(initial_asset, "id", None),
            )
            show_error(
                str(error),
                title=tr("dashboard.asset.error.save_title", "Ошибка сохранения актива"),
                parent=dialog,
            )
            return
        dialog.destroy()
        on_saved()

    ttk.Button(buttons, text=tr("common.cancel", "Отмена"), command=_close).pack(
        side=tk.LEFT, padx=(0, 8)
    )
    save_button = ttk.Button(
        buttons,
        text=tr("dashboard.asset.save", "Сохранить актив"),
        style="Primary.TButton",
        command=_save,
    )
    save_button.pack(side=tk.LEFT)

    tracked_vars = [name_var, category_var, currency_var, description_var]
    if initial_asset is None:
        tracked_vars.append(created_at_var)
    for var in tracked_vars:
        var.trace_add("write", _validate_form)
    _validate_form()

    dialog.protocol("WM_DELETE_WINDOW", _close)
    dialog.update_idletasks()

    center_dialog(dialog, parent, min_width=560, min_height=220)
    dialog.deiconify()
    dialog.grab_set()
    name_entry.focus_set()
    parent.wait_window(dialog)


def show_manage_assets_dialog(
    parent: tk.Misc,
    *,
    context: DashboardTabContext,
    on_saved: Callable[[], None],
) -> None:
    dialog = tk.Toplevel(parent)
    dialog.withdraw()
    dialog.title(tr("dashboard.assets.manage_title", "Управление активами"))
    dialog.transient(parent.winfo_toplevel())
    dialog.minsize(760, 360)
    dialog.grid_columnconfigure(0, weight=1)
    dialog.grid_rowconfigure(0, weight=1)

    content = ttk.Frame(dialog, padding=12)
    content.grid(row=0, column=0, sticky="nsew")
    content.grid_columnconfigure(0, weight=1)
    content.grid_rowconfigure(1, weight=1)

    ttk.Label(
        content,
        text=tr("dashboard.assets.manage_title", "Управление активами"),
        font=("Segoe UI", 11, "bold"),
    ).grid(row=0, column=0, sticky="w")

    tree = ttk.Treeview(
        content,
        columns=("name", "category", "currency", "created_at", "status"),
        show="headings",
        height=10,
    )
    tree.grid(row=1, column=0, sticky="nsew", pady=(10, 0))
    tree.heading("name", text=tr("common.name", "Название"))
    tree.heading("category", text=tr("common.category_short", "Категория"))
    tree.heading("currency", text=tr("common.currency_short", "Валюта"))
    tree.heading("created_at", text=tr("common.created_short", "Создан"))
    tree.heading("status", text=tr("common.status", "Статус"))
    tree.column("name", width=220)
    tree.column("category", width=100)
    tree.column("currency", width=80, anchor="center")
    tree.column("created_at", width=110, anchor="center")
    tree.column("status", width=90, anchor="center")
    enable_treeview_column_autosize(tree, columns=("name",), max_width=360)

    actions = ttk.Frame(content)
    actions.grid(row=2, column=0, sticky="ew", pady=(12, 0))

    assets_by_id: dict[str, Asset] = {}
    edit_button = ttk.Button(
        actions, text=tr("common.edit", "Редактировать"), command=lambda: _edit_asset()
    )
    deactivate_button = ttk.Button(
        actions,
        text=tr("dashboard.asset.deactivate", "Деактивировать"),
        command=lambda: _deactivate_asset(),
    )

    def _block_separator_resize(event: tk.Event) -> str | None:
        if isinstance(event.widget, ttk.Treeview):
            region = event.widget.identify_region(event.x, event.y)
            if region == "separator":
                return "break"
        return None

    tree.bind("<Button-1>", _block_separator_resize)

    def _selected_asset() -> Asset | None:
        selected = tree.selection()
        if not selected:
            return None
        return assets_by_id.get(str(selected[0]))

    def _refresh_action_state(*_args) -> None:
        can_edit, can_deactivate = _asset_actions_state(_selected_asset())
        set_button_enabled(edit_button, can_edit)
        set_button_enabled(deactivate_button, can_deactivate)

    def _refresh_assets() -> None:
        nonlocal assets_by_id
        tree.delete(*tree.get_children())
        assets = list(context.controller.get_assets(active_only=False))
        assets_by_id = {str(asset.id): asset for asset in assets}
        for asset in assets:
            tree.insert(
                "",
                "end",
                iid=str(asset.id),
                values=(
                    str(asset.name),
                    str(asset.category.value),
                    str(asset.currency),
                    str(asset.created_at),
                    tr("common.active", "Активен")
                    if bool(asset.is_active)
                    else tr("common.inactive", "Неактивен"),
                ),
            )
        _refresh_action_state()

    def _create_asset() -> None:
        show_asset_editor_dialog(
            dialog, context=context, initial_asset=None, on_saved=_after_change
        )

    def _edit_asset() -> None:
        asset = _selected_asset()
        if asset is None:
            show_info(
                tr("dashboard.asset.select_edit", "Сначала выберите актив для редактирования."),
                title=tr("dashboard.assets.manage_title", "Управление активами"),
                parent=dialog,
            )
            return
        show_asset_editor_dialog(
            dialog, context=context, initial_asset=asset, on_saved=_after_change
        )

    def _deactivate_asset() -> None:
        asset = _selected_asset()
        if asset is None:
            show_info(
                tr("dashboard.asset.select_deactivate", "Сначала выберите актив для деактивации."),
                title=tr("dashboard.assets.manage_title", "Управление активами"),
                parent=dialog,
            )
            return
        if not bool(asset.is_active):
            show_info(
                tr("dashboard.asset.already_inactive", "Выбранный актив уже неактивен."),
                title=tr("dashboard.assets.manage_title", "Управление активами"),
                parent=dialog,
            )
            return
        confirmed = ask_confirm(
            tr(
                "dashboard.asset.deactivate.confirm",
                "Деактивировать актив '{name}'?",
                name=asset.name,
            ),
            title=tr("dashboard.asset.deactivate.title", "Деактивация актива"),
            parent=dialog,
        )
        if not confirmed:
            return
        try:
            context.controller.deactivate_asset(asset.id)
        except (DomainError, ValueError, TypeError, RuntimeError) as error:
            log_ui_error(logger, "UI_DASH_ASSET_DEACTIVATE_FAILED", error, asset_id=asset.id)
            show_error(str(error), title="Ошибка деактивации актива", parent=dialog)
            return
        _after_change()

    def _after_change() -> None:
        _refresh_assets()
        on_saved()

    ttk.Button(
        actions,
        text=tr("common.create", "Создать"),
        style="Primary.TButton",
        command=_create_asset,
    ).pack(side=tk.LEFT)
    edit_button.pack(side=tk.LEFT, padx=(8, 0))
    deactivate_button.pack(side=tk.LEFT, padx=(8, 0))
    ttk.Button(actions, text=tr("common.close", "Закрыть"), command=dialog.destroy).pack(
        side=tk.RIGHT
    )

    tree.bind("<<TreeviewSelect>>", _refresh_action_state)
    _refresh_assets()
    dialog.update_idletasks()

    center_dialog(dialog, parent, min_width=760, min_height=360)
    dialog.deiconify()
    dialog.grab_set()
    parent.wait_window(dialog)
