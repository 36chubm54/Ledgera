"""Background and mutation flows for the operations tab."""

from __future__ import annotations

import logging
import os
import tkinter as tk
from collections.abc import Callable
from tkinter import filedialog
from typing import Any, Protocol

from app_paths import get_exports_dir
from domain.errors import DomainError
from domain.import_policy import ImportPolicy
from domain.import_result import ImportResult
from gui.helpers import open_in_file_manager
from gui.i18n import tr
from gui.logging_utils import log_ui_error
from gui.ui_helpers import ask_confirm, show_error, show_info, show_warning

logger = logging.getLogger(__name__)


def delete_selected_flow(
    *,
    context: Any,
    records_tree: SelectableTreeLike,
    refresh_after_mutation: Callable[[], None],
) -> None:
    selection = records_tree.selection()
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
            show_info(tr("operations.transfer.deleted", "Перевод #{id} удален.", id=transfer_id))
        elif context.controller.delete_record(repository_index):
            show_info(tr("operations.deleted", "Запись удалена."))
        else:
            show_error(tr("operations.error.delete_failed", "Не удалось удалить запись."))
            return
        refresh_after_mutation()
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


def delete_all_flow(
    *,
    context: Any,
    refresh_after_mutation: Callable[[], None],
) -> None:
    confirm = ask_confirm(
        tr(
            "operations.delete_all.confirm",
            "Удалить все записи? Это действие нельзя отменить.",
        ),
        title=tr("operations.delete_all.title", "Подтвердите удаление"),
    )
    if not confirm:
        return
    context.controller.delete_all_records()
    show_info(tr("operations.deleted_all_done", "Все записи удалены."))
    refresh_after_mutation()


def import_records_flow(
    *,
    parent: tk.Misc,
    context: Any,
    import_formats: dict[str, dict[str, str]],
    format_name: str,
    mode_label: str,
    show_import_preview_dialog: Callable[..., bool],
    refresh_after_mutation: Callable[[], None],
) -> None:
    policy = context._import_policy_from_ui(mode_label)
    cfg = import_formats.get(format_name)
    if not cfg:
        show_error(
            tr(
                "operations.error.import_format",
                "Неподдерживаемый формат импорта: {fmt}",
                fmt=format_name,
            )
        )
        return

    filepath = filedialog.askopenfilename(
        defaultextension=cfg["ext"],
        filetypes=[(f"{format_name} files", f"*{cfg['ext']}"), ("All files", "*.*")],
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
        return context.controller.import_records(format_name, filepath, policy, dry_run=True)

    def commit_task() -> ImportResult:
        return context.controller.import_records(format_name, filepath, policy, dry_run=False)

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
        refresh_after_mutation()

    def on_error(exc: BaseException) -> None:
        if isinstance(exc, FileNotFoundError):
            show_error(tr("common.file_not_found", "Файл не найден: {filepath}", filepath=filepath))
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
            policy_label=mode_label,
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


def export_records_flow(
    *,
    context: Any,
    import_formats: dict[str, dict[str, str]],
    format_name: str,
    asksaveasfilename: Callable[..., str],
) -> None:
    cfg = import_formats.get(format_name)
    if not cfg or format_name == "JSON":
        show_error(
            tr(
                "operations.export.unsupported",
                "Этот формат не поддерживается для экспорта операций.",
            )
        )
        return
    if not ask_confirm(
        tr(
            "operations.export.warning",
            "Экспорт создаст читаемый файл с финансовыми данными. "
            "Сохраняйте его только в доверенное место. Продолжить?",
        ),
        title=tr("common.confirm", "Подтверждение"),
    ):
        return
    exports_dir = get_exports_dir()
    exports_dir.mkdir(parents=True, exist_ok=True)
    filepath = asksaveasfilename(
        defaultextension=cfg["ext"],
        filetypes=[(f"{cfg['desc']} files", f"*{cfg['ext']}"), ("All files", "*.*")],
        title=tr(
            "operations.export.save_as", "Сохранить операции как {format}", format=cfg["desc"]
        ),
        initialdir=str(exports_dir),
    )
    if not filepath:
        return

    def task() -> None:
        from gui.exporters import export_records

        records = context.repository.load_all()
        transfers = context.repository.load_transfers()
        export_records(records, filepath, format_name.lower(), transfers=transfers)

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
        busy_message=tr("operations.busy.export", "Экспортируем {format}...", format=cfg["desc"]),
    )


class SelectableTreeLike(Protocol):
    def selection(self) -> tuple[str, ...]: ...
