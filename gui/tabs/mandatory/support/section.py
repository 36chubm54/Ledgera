from __future__ import annotations

import logging
import os
import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass
from tkinter import filedialog, ttk
from typing import Any

from app_paths import get_exports_dir
from domain.import_result import ImportResult
from gui.helpers import open_in_file_manager
from gui.i18n import tr
from gui.ui_dialogs import messagebox_compat as messagebox
from gui.ui_helpers import safe_destroy
from gui.ui_theme import PAD_SM, PAD_XS, create_card_section

from .actions import (
    MandatorySectionActionContext,
    MessageBoxLike,
    selected_mandatory_index,
)
from .actions import (
    delete_all_mandatory as delete_all_mandatory_action,
)
from .actions import (
    delete_mandatory as delete_mandatory_action,
)
from .actions import (
    save_add_to_records as save_add_to_records_action,
)
from .actions import (
    save_create_form as save_create_form_action,
)
from .actions import (
    save_edit_form as save_edit_form_action,
)
from .forms import (
    build_add_mandatory_panel,
    build_add_to_records_panel,
    build_edit_mandatory_panel,
    next_grid_row,
    refresh_add_form_wallets,
)
from .keyboard import (
    bind_focus_navigation,
    build_inline_action_buttons,
)
from .tree_section import (
    bind_mandatory_horizontal_scroll,
    build_mandatory_actions_row,
    build_mandatory_tree,
    populate_mandatory_tree,
)

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class MandatorySectionBindings:
    refresh: Callable[[], None]
    add_mandatory: Callable[[], None]
    edit_mandatory: Callable[[], None]
    add_to_records: Callable[[], None]
    delete_mandatory: Callable[[], None]


def build_mandatory_section(
    parent_panel: tk.Frame | ttk.Frame,
    *,
    context: Any,
    import_formats: dict[str, dict[str, str]],
    refresh_wallets: Callable[[], None],
    base_currency_code: str,
    messagebox_module: MessageBoxLike = messagebox,
    row_index: int = 1,
) -> MandatorySectionBindings:
    pad_x = PAD_SM
    pad_y = PAD_XS

    parent_panel.grid_rowconfigure(row_index, weight=1)
    parent_panel.grid_columnconfigure(0, weight=2, uniform="mandatory")
    parent_panel.grid_columnconfigure(1, weight=5, uniform="mandatory")

    form_card = create_card_section(
        parent_panel,
        tr("mandatory.create_card", "Новый обязательный расход"),
    )
    form_card.grid(row=row_index, column=0, sticky="nsew", padx=(0, PAD_SM))
    form_frame = form_card.winfo_children()[-1]
    form_frame.grid_columnconfigure(0, weight=1)

    journal_card = create_card_section(
        parent_panel,
        tr("mandatory.journal_card", "Журнал обязательных расходов"),
    )
    journal_card.grid(row=row_index, column=1, sticky="nsew", padx=(PAD_SM, 0))
    journal_frame = journal_card.winfo_children()[-1]
    journal_frame.grid_rowconfigure(0, weight=1)
    journal_frame.grid_columnconfigure(0, weight=1)

    create_form = build_add_mandatory_panel(
        form_frame,
        controller=context.controller,
        base_currency_code=base_currency_code,
        row_index=0,
        inline=False,
    )

    mand_tree, _mand_yscroll, mand_xscroll = build_mandatory_tree(journal_frame)
    bind_mandatory_horizontal_scroll(mand_tree, mand_xscroll)

    inline_frame = ttk.Frame(journal_frame)
    inline_frame.grid_columnconfigure(0, weight=1)
    current_panel: dict[str, tk.Frame | ttk.Frame | None] = {
        "report": None,
        "edit": None,
    }

    def refresh_mandatory() -> None:
        populate_mandatory_tree(
            mand_tree,
            context=context,
            base_currency_code=base_currency_code,
        )
        refresh_add_form_wallets(create_form, context.controller)

    def show_inline_frame() -> None:
        inline_frame.grid(
            row=2,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=pad_x,
            pady=(0, PAD_SM),
        )

    def close_inline_panels() -> None:
        for key in ("report", "edit"):
            panel = current_panel[key]
            if panel is not None:
                safe_destroy(panel)
                current_panel[key] = None
        inline_frame.grid_forget()

    def action_runtime() -> MandatorySectionActionContext:
        return MandatorySectionActionContext(
            context=context,
            refresh_mandatory=refresh_mandatory,
            refresh_wallets=refresh_wallets,
            close_inline_panels=close_inline_panels,
            base_currency_code=base_currency_code,
            messagebox_module=messagebox_module,
            logger=logger,
        )

    def save_create() -> None:
        save_create_form_action(create_form, action_runtime())

    create_button = ttk.Button(
        create_form.panel,
        text=tr("mandatory.create", "Создать обязательный расход"),
        style="Primary.TButton",
        command=save_create,
    )
    create_button.grid(row=next_grid_row(create_form.panel), column=0, columnspan=4, pady=8)
    bind_focus_navigation(
        [
            create_form.amount_entry,
            create_form.currency_entry,
            create_form.wallet_menu,
            create_form.category_entry,
            create_form.description_entry,
            create_form.period_combo,
            create_form.date_entry,
            create_button,
        ],
        submit_action=save_create,
    )

    def edit_mandatory_inline() -> None:
        index = selected_mandatory_index(
            mand_tree,
            messagebox_module=messagebox_module,
            missing_message=tr(
                "mandatory.error.select_edit",
                "Выберите обязательный расход для редактирования.",
            ),
        )
        if index is None:
            return
        expenses = context.controller.load_mandatory_expenses()
        if not (0 <= index < len(expenses)):
            return
        expense = expenses[index]

        close_inline_panels()
        show_inline_frame()

        form = build_edit_mandatory_panel(
            inline_frame,
            controller=context.controller,
            expense=expense,
        )
        current_panel["edit"] = form.panel

        def save_edit() -> None:
            save_edit_form_action(form, expense=expense, runtime=action_runtime())

        action_buttons = build_inline_action_buttons(
            form.panel,
            row_index=4,
            on_save=save_edit,
            on_cancel=close_inline_panels,
        )
        bind_focus_navigation(
            [
                form.amount_base_entry,
                form.wallet_menu,
                form.period_combo,
                form.date_entry,
                action_buttons.save_button,
                action_buttons.cancel_button,
            ],
            submit_action=save_edit,
            cancel_action=close_inline_panels,
        )
        form.amount_base_entry.focus_set()

    def add_to_records_inline() -> None:
        index = selected_mandatory_index(
            mand_tree,
            messagebox_module=messagebox_module,
            missing_message=tr(
                "mandatory.error.select_add_to_records",
                "Выберите обязательный расход для добавления в записи.",
            ),
        )
        if index is None:
            return

        close_inline_panels()
        show_inline_frame()

        form = build_add_to_records_panel(
            inline_frame,
            controller=context.controller,
        )
        current_panel["report"] = form.panel

        def save() -> None:
            save_add_to_records_action(index, form, action_runtime())

        action_buttons = build_inline_action_buttons(
            form.panel,
            row_index=2,
            on_save=save,
            on_cancel=close_inline_panels,
        )
        bind_focus_navigation(
            [
                form.date_entry,
                form.wallet_menu,
                action_buttons.save_button,
                action_buttons.cancel_button,
            ],
            submit_action=save,
            cancel_action=close_inline_panels,
        )
        form.date_entry.focus_set()

    def delete_mandatory() -> None:
        index = selected_mandatory_index(
            mand_tree,
            messagebox_module=messagebox_module,
            missing_message=tr(
                "mandatory.error.select_delete",
                "Выберите обязательный расход для удаления.",
            ),
        )
        if index is None:
            return
        delete_mandatory_action(index, action_runtime())

    def delete_all_mandatory() -> None:
        delete_all_mandatory_action(action_runtime())

    format_var = tk.StringVar(value="CSV")

    def import_mand() -> None:
        fmt = format_var.get()
        cfg = import_formats.get(fmt)
        if not cfg:
            messagebox_module.showerror(
                tr("common.error", "Ошибка"),
                tr("common.unsupported_format", "Неподдерживаемый формат: {fmt}", fmt=fmt),
            )
            return

        filepath = filedialog.askopenfilename(
            defaultextension=cfg["ext"],
            filetypes=[(f"{cfg['desc']} files", f"*{cfg['ext']}"), ("All files", "*.*")],
            title=tr(
                "mandatory.import.select_file",
                "Выберите файл {desc} для импорта обязательных расходов",
                desc=cfg["desc"],
            ),
        )
        if not filepath:
            return

        if not messagebox_module.askyesno(
            tr("common.confirm", "Подтверждение"),
            tr(
                "mandatory.import.confirm",
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

            messagebox_module.showinfo(
                tr("common.done", "Готово"),
                tr(
                    "mandatory.import.success",
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
                messagebox_module.showerror(
                    tr("common.error", "Ошибка"),
                    tr("common.file_not_found", "Файл не найден: {filepath}", filepath=filepath),
                )
                return
            messagebox_module.showerror(
                tr("common.error", "Ошибка"),
                tr(
                    "mandatory.import.error",
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
                "mandatory.import.busy",
                "Импортируем обязательные расходы из {desc}...",
                desc=cfg["desc"],
            ),
        )

    def export_mand() -> None:
        fmt = format_var.get()
        expenses = context.controller.load_mandatory_expenses()
        if not expenses:
            messagebox_module.showinfo(
                tr("mandatory.export.empty_title", "Нет расходов"),
                tr("mandatory.export.empty", "Нет обязательных расходов для экспорта."),
            )
            return
        if not messagebox_module.askyesno(
            tr("common.confirm", "Подтверждение"),
            tr(
                "mandatory.export.warning",
                "Экспорт создаст читаемый файл с финансовыми данными. "
                "Сохраняйте его только в доверенное место. Продолжить?",
            ),
        ):
            return

        exports_dir = get_exports_dir()
        exports_dir.mkdir(parents=True, exist_ok=True)
        filepath = filedialog.asksaveasfilename(
            defaultextension=f".{fmt.lower()}",
            title=tr("mandatory.export.save", "Сохранить обязательные расходы"),
            initialdir=str(exports_dir),
        )
        if not filepath:
            return

        def task() -> None:
            from gui.exporters import export_mandatory_expenses

            export_mandatory_expenses(expenses, filepath, fmt.lower())

        def on_success(_: Any) -> None:
            messagebox_module.showinfo(
                tr("common.done", "Готово"),
                tr(
                    "mandatory.export.success",
                    "Обязательные расходы экспортированы в {filepath}",
                    filepath=filepath,
                ),
            )
            open_in_file_manager(os.path.dirname(filepath))

        context._run_background(
            task,
            on_success=on_success,
            busy_message=tr(
                "mandatory.export.busy",
                "Экспортируем обязательные расходы в {fmt}...",
                fmt=fmt,
            ),
        )

    build_mandatory_actions_row(
        journal_frame,
        format_var=format_var,
        on_edit=edit_mandatory_inline,
        on_add_to_records=add_to_records_inline,
        on_delete=delete_mandatory,
        on_delete_all=delete_all_mandatory,
        on_refresh=refresh_mandatory,
        on_import=import_mand,
        on_export=export_mand,
        pad_x=pad_x,
        pad_y=pad_y,
        row_index=3,
    )

    return MandatorySectionBindings(
        refresh=refresh_mandatory,
        add_mandatory=save_create,
        edit_mandatory=edit_mandatory_inline,
        add_to_records=add_to_records_inline,
        delete_mandatory=delete_mandatory,
    )
