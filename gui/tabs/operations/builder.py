"""Operations tab builder."""

from __future__ import annotations

import logging
import os
import tkinter as tk
from tkinter import filedialog, ttk
from typing import Any

from domain.errors import DomainError
from domain.import_policy import ImportPolicy
from domain.import_result import ImportResult
from gui.helpers import open_in_file_manager
from gui.i18n import tr
from gui.logging_utils import log_ui_error
from gui.tabs.operations_support import refresh_operation_views, show_import_preview_dialog
from gui.ui_helpers import ask_confirm, show_error, show_info, show_warning
from gui.ui_theme import PAD_LG, PAD_SM, PAD_XL

from .contracts import OperationsTabBindings, OperationsTabContext
from .form_section import build_operation_form_section
from .inline_editors import InlineEditors, build_inline_editors
from .journal_section import JournalSection, build_journal_section
from .transfer_section import build_transfer_section

logger = logging.getLogger(__name__)


def build_operations_tab(
    parent: tk.Frame | ttk.Frame,
    context: OperationsTabContext,
    import_formats: dict[str, dict[str, str]],
) -> OperationsTabBindings:
    parent.grid_columnconfigure(0, weight=2, uniform="operations")
    parent.grid_columnconfigure(1, weight=5, uniform="operations")
    parent.grid_rowconfigure(0, weight=1)

    left_frame = ttk.Frame(parent)
    left_frame.grid(row=0, column=0, sticky="nsew", padx=(PAD_XL, PAD_SM), pady=PAD_LG)
    left_frame.grid_columnconfigure(0, weight=1)
    left_frame.grid_rowconfigure(0, weight=1)

    paned = ttk.PanedWindow(left_frame, orient=tk.VERTICAL)
    paned.grid(row=0, column=0, sticky="nsew")

    def _refresh_after_mutation() -> None:
        refresh_operation_views(context)
        form_section.refresh_category_combo()

    form_section = build_operation_form_section(
        paned,
        context=context,
        logger=logger,
        on_saved=_refresh_after_mutation,
    )

    inline_editors: InlineEditors | None = None
    journal_section: JournalSection

    def delete_selected() -> None:
        selection = journal_section.records_tree.selection()
        if not selection:
            show_error(tr("operations.error.select_first", "Сначала выберите запись."))
            return
        record_id = selection[0]
        repository_index = context._record_id_to_repo_index.get(record_id)
        if repository_index is None:
            show_error(tr("operations.error.unavailable", "Выбранная запись больше недоступна."))
            context._refresh_list()
            return
        try:
            transfer_id = context.controller.transfer_id_by_repository_index(repository_index)
            if transfer_id is not None:
                context.controller.delete_transfer(transfer_id)
                show_info(
                    tr("operations.transfer.deleted", "Перевод #{id} удален.", id=transfer_id)
                )
            elif context.controller.delete_record(repository_index):
                show_info(tr("operations.deleted", "Запись удалена."))
            else:
                show_error(tr("operations.error.delete_failed", "Не удалось удалить запись."))
                return
            _refresh_after_mutation()
        except (DomainError, ValueError, TypeError, RuntimeError) as error:
            log_ui_error(
                logger,
                "UI_OPS_DELETE_RECORD_FAILED",
                error,
                record_ui_id=record_id,
                repository_index=repository_index,
            )
            show_error(
                tr(
                    "operations.error.delete_failed_with_error",
                    "Не удалось удалить запись: {error}",
                    error=error,
                )
            )

    def edit_selected_record_inline() -> None:
        if inline_editors is None:
            return
        inline_editors.edit_selected_record_inline()

    def delete_all() -> None:
        confirm = ask_confirm(
            tr(
                "operations.delete_all.confirm",
                "Удалить все записи? Это действие нельзя отменить.",
            ),
            title=tr("operations.delete_all.title", "Подтвердите удаление"),
        )
        if confirm:
            context.controller.delete_all_records()
            show_info(tr("operations.deleted_all_done", "Все записи удалены."))
            _refresh_after_mutation()

    def import_records_data() -> None:
        policy = context._import_policy_from_ui(journal_section.import_mode_key_var.get())
        fmt = journal_section.import_format_var.get()
        cfg = import_formats.get(fmt)
        if not cfg:
            show_error(
                tr(
                    "operations.error.import_format",
                    "Неподдерживаемый формат импорта: {fmt}",
                    fmt=fmt,
                )
            )
            return

        filepath = filedialog.askopenfilename(
            defaultextension=cfg["ext"],
            filetypes=[(f"{fmt} files", f"*{cfg['ext']}"), ("All files", "*.*")],
            title=tr(
                "operations.import.select_file",
                "Выберите файл {format} для импорта",
                format=cfg["desc"],
            ),
        )
        if not filepath:
            return

        if policy == ImportPolicy.CURRENT_RATE:
            show_warning(
                tr(
                    "operations.import.current_rate.body",
                    "В режиме CURRENT_RATE курсы валют будут зафиксированы на момент импорта.",
                ),
                title=tr("operations.import.current_rate.title", "Импорт по текущему курсу"),
            )

        def preview_task() -> ImportResult:
            return context.controller.import_records(fmt, filepath, policy, dry_run=True)

        def commit_task() -> ImportResult:
            return context.controller.import_records(fmt, filepath, policy, dry_run=False)

        def on_commit_success(result: ImportResult) -> None:
            details = ""
            if result.skipped or result.errors:
                details = f"\nПропущено строк: {result.skipped}.\nПервые ошибки:\n- " + "\n- ".join(
                    result.errors[:5]
                )
            show_info(
                tr(
                    "operations.import.success",
                    "Импортировано записей: {count} ({format}).\nТекущие записи были заменены.",
                    count=result.imported,
                    format=cfg["desc"],
                )
                + details,
                title=tr("common.done", "Готово"),
            )
            _refresh_after_mutation()

        def on_error(exc: BaseException) -> None:
            if isinstance(exc, FileNotFoundError):
                show_error(
                    tr("common.file_not_found", "Файл не найден: {filepath}", filepath=filepath)
                )
                return
            show_error(
                tr(
                    "operations.import.error",
                    "Не удалось импортировать {format}: {error}",
                    format=cfg["desc"],
                    error=exc,
                )
            )

        def on_preview_success(preview: ImportResult) -> None:
            confirmed = show_import_preview_dialog(
                parent=parent,
                filepath=filepath,
                policy_label=journal_section.import_mode_label_var.get(),
                preview=preview,
                force=False,
            )
            if not confirmed:
                return
            context._run_background(
                commit_task,
                on_success=on_commit_success,
                on_error=on_error,
                busy_message=tr(
                    "operations.busy.import", "Импортируем {format}...", format=cfg["desc"]
                ),
            )

        context._run_background(
            preview_task,
            on_success=on_preview_success,
            on_error=on_error,
            busy_message=tr(
                "operations.busy.validate", "Проверяем импорт {format}...", format=cfg["desc"]
            ),
        )

    def export_records_data() -> None:
        fmt = journal_section.import_format_var.get()
        cfg = import_formats.get(fmt)
        if not cfg or fmt == "JSON":
            show_error(
                tr(
                    "operations.export.unsupported",
                    "Этот формат не поддерживается для экспорта операций.",
                )
            )
            return
        filepath = filedialog.asksaveasfilename(
            defaultextension=cfg["ext"],
            filetypes=[(f"{cfg['desc']} files", f"*{cfg['ext']}"), ("All files", "*.*")],
            title=tr(
                "operations.export.save_as", "Сохранить операции как {format}", format=cfg["desc"]
            ),
        )
        if not filepath:
            return

        def task() -> None:
            from gui.exporters import export_records

            records = context.repository.load_all()
            transfers = context.repository.load_transfers()
            export_records(records, filepath, fmt.lower(), transfers=transfers)

        def on_success(_: Any) -> None:
            show_info(
                tr(
                    "operations.export.success",
                    "Операции экспортированы в:\n{filepath}",
                    filepath=filepath,
                )
            )
            open_in_file_manager(os.path.dirname(filepath))

        context._run_background(
            task,
            on_success=on_success,
            busy_message=tr(
                "operations.busy.export", "Экспортируем {format}...", format=cfg["desc"]
            ),
        )

    format_options = [
        format_name for format_name in ("CSV", "XLSX") if format_name in import_formats
    ]

    journal_section = build_journal_section(
        parent,
        format_options=format_options,
        on_delete_selected=delete_selected,
        on_edit_selected=edit_selected_record_inline,
        on_refresh_list=context._refresh_list,
        on_delete_all=delete_all,
        on_import=import_records_data,
        on_export=export_records_data,
    )

    transfer_section = build_transfer_section(
        paned,
        context=context,
        logger=logger,
        base_currency_code=form_section.base_currency_code,
        on_saved=_refresh_after_mutation,
    )

    inline_editors = build_inline_editors(
        list_frame=journal_section.list_frame,
        records_tree=journal_section.records_tree,
        context=context,
        logger=logger,
        refresh_category_combo=form_section.refresh_category_combo,
        sync_tag_color_from_input=form_section.sync_tag_color_from_input,
        base_currency_code=form_section.base_currency_code,
        is_kzt_currency=form_section.is_kzt_currency,
        amount_edit_label_text=form_section.amount_edit_label_text,
        amount_edit_tooltip_text=form_section.amount_edit_tooltip_text,
        after_update=_refresh_after_mutation,
    )

    context._refresh_list()

    return OperationsTabBindings(
        records_tree=journal_section.records_tree,
        tags_tree=journal_section.tags_tree,
        refresh_operation_wallet_menu=form_section.refresh_operation_wallet_menu,
        refresh_transfer_wallet_menus=transfer_section.refresh_transfer_wallet_menus,
        set_type_income=form_section.set_type_income,
        set_type_expense=form_section.set_type_expense,
        save_record=form_section.save_record,
        select_first=journal_section.select_first,
        select_last=journal_section.select_last,
        delete_selected=delete_selected,
        delete_all=delete_all,
        edit_selected=edit_selected_record_inline,
        inline_editor_active=inline_editors.inline_editor_active,
    )
