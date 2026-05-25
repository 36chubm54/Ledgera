from __future__ import annotations

import logging
import os
from collections.abc import Callable
from typing import Any

from app_paths import get_exports_dir
from gui.helpers import open_in_file_manager
from gui.i18n import tr
from gui.logging_utils import log_ui_error
from gui.ui_helpers import ask_confirm, show_error, show_info
from services.analytics.report import build_category_group_rows

logger = logging.getLogger(__name__)


def run_generate_flow(owner: Any) -> None:
    owner._refresh_wallets()
    filters = owner._current_filters()
    owner._set_reports_busy(True)

    def task():
        return owner._controller.generate(filters)

    def on_success(result: Any) -> None:
        owner._last_result = result
        owner._group_drill_category = None
        owner._refresh_summary_only()
        owner._refresh_operations_table()
        owner._refresh_monthly_table()
        owner._refresh_category_sources()
        owner._set_reports_busy(False)

    def on_error(error: BaseException) -> None:
        owner._set_reports_busy(False)
        if isinstance(error, ValueError):
            show_error(str(error), title=tr("common.error", "Ошибка"))
            return
        log_ui_error(logger, "UI_REPORTS_GENERATE_FAILED", error)
        show_error(
            tr("reports.error.generate", "Не удалось сформировать отчет: {error}", error=error),
            title=tr("common.error", "Ошибка"),
        )

    owner._context._run_background(
        task,
        on_success=on_success,
        on_error=on_error,
        busy_message=tr("reports.generate.busy", "Формируем отчет..."),
        block_ui=False,
    )


def run_export_flow(
    owner: Any,
    fmt: str,
    *,
    asksaveasfilename: Callable[..., str],
    report_to_csv: Callable[..., None],
) -> None:
    result = owner._last_result
    if result is None:
        show_error(
            tr("reports.error.generate_first", "Сначала сформируйте отчет."),
            title=tr("common.error", "Ошибка"),
        )
        return

    fmt = (fmt or "csv").strip().lower()
    if fmt not in ("csv", "xlsx", "pdf"):
        show_error(
            tr(
                "reports.error.unsupported_format",
                "Неподдерживаемый формат экспорта: {fmt}",
                fmt=fmt,
            ),
            title=tr("common.error", "Ошибка"),
        )
        return

    drill_category = (owner._group_drill_category or "").strip()
    export_category_only = bool(owner.group_var.get()) and bool(drill_category)
    if not ask_confirm(
        tr(
            "reports.export.warning",
            "Экспорт создаст читаемый файл с финансовыми данными. "
            "Сохраняйте его только в доверенное место. Продолжить?",
        ),
        title=tr("common.confirm", "Подтверждение"),
    ):
        return

    exports_dir = get_exports_dir()
    exports_dir.mkdir(parents=True, exist_ok=True)
    filepath = _select_export_filepath(fmt, str(exports_dir), asksaveasfilename)
    if not filepath:
        return
    owner._set_reports_busy(True)

    def task() -> None:
        base_currency = owner._context.controller.get_base_currency_code()
        export_grouped_summary = bool(owner.group_var.get()) and not drill_category
        if export_grouped_summary:
            from gui.exporters import export_grouped_report

            grouped_rows = [
                (row.category, row.operations_count, row.total_base)
                for row in build_category_group_rows(result.operations)
            ]
            export_grouped_report(
                tr(
                    "reports.export.grouped_title",
                    "{title} - По категориям",
                    title=result.report.statement_title,
                ),
                grouped_rows,
                filepath,
                fmt,
                base_currency=base_currency,
            )
            return

        report_to_export = (
            result.report.filter_by_category(drill_category)
            if export_category_only
            else result.report
        )
        if fmt == "csv":
            report_to_csv(report_to_export, filepath, base_currency=base_currency)
            return

        from gui.exporters import export_report

        export_report(
            report_to_export,
            filepath,
            fmt,
            debts=owner._context.controller.get_debts(result.filters.wallet_id),
            base_currency=base_currency,
        )

    def on_success(_: object) -> None:
        owner._set_reports_busy(False)
        show_info(
            "\n\n".join(
                [
                    tr(
                        "reports.export.success",
                        "Экспортировано в {filepath}",
                        filepath=filepath,
                    ),
                    tr(
                        "reports.export.note",
                        "Экспорт использует суммы в валюте базы и может отличаться "
                        "от текущего отображения в выбранной валюте показа.",
                    ),
                ]
            ),
            title=tr("common.done", "Готово"),
        )
        open_in_file_manager(os.path.dirname(filepath))

    def on_error(error: BaseException) -> None:
        owner._set_reports_busy(False)
        log_ui_error(logger, "UI_REPORTS_EXPORT_FAILED", error, filepath=filepath)
        show_error(
            tr("reports.export.error", "Не удалось экспортировать: {error}", error=error),
            title=tr("common.error", "Ошибка"),
        )

    owner._context._run_background(
        task,
        on_success=on_success,
        on_error=on_error,
        busy_message=tr("reports.export.busy", "Экспортируем отчет..."),
        block_ui=False,
    )


def _select_export_filepath(
    fmt: str,
    exports_dir: str,
    asksaveasfilename: Callable[..., str],
) -> str:
    if fmt == "csv":
        return asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv")],
            title=tr("reports.export.save_csv", "Сохранить CSV"),
            initialdir=exports_dir,
        )
    if fmt == "xlsx":
        return asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Excel", "*.xlsx")],
            title=tr("reports.export.save_xlsx", "Сохранить XLSX"),
            initialdir=exports_dir,
        )
    return asksaveasfilename(
        defaultextension=".pdf",
        filetypes=[("PDF", "*.pdf")],
        title=tr("reports.export.save_pdf", "Сохранить PDF"),
        initialdir=exports_dir,
    )
