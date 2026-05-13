"""Reports tab — Summaries, Transaction Statements and Grouped Reports"""

from __future__ import annotations

import logging
import os
import tkinter as tk
from tkinter import filedialog, ttk
from typing import Any, Protocol

from gui.helpers import open_in_file_manager
from gui.i18n import tr
from gui.logging_utils import log_ui_error
from gui.tabs.reports_controller import ReportsController
from gui.tabs.reports_layout import ReportsUiHandles, build_reports_layout
from gui.tabs.reports_render import (
    apply_group_ui_state,
    apply_table_ui_state,
    refresh_category_sources,
    refresh_monthly_table,
    refresh_operations_table,
    refresh_summary_only,
    refresh_wallets,
)
from gui.ui_helpers import show_error, show_info
from services.report_service import ReportFilters, build_category_group_rows
from utils.csv_utils import report_to_csv

logger = logging.getLogger(__name__)


class ReportsTabContext(Protocol):
    controller: Any
    currency: Any


def build_reports_tab(parent: tk.Frame | ttk.Frame, context: ReportsTabContext) -> ReportsFrame:
    frame = ReportsFrame(parent, context)
    frame.grid(row=0, column=0, sticky="nsew")
    parent.grid_rowconfigure(0, weight=1)
    parent.grid_columnconfigure(0, weight=1)
    return frame


class ReportsFrame(ttk.Frame):
    def __init__(self, parent: tk.Misc, context: ReportsTabContext) -> None:
        super().__init__(parent, padding=10)
        self._context = context
        self._controller = ReportsController(context.controller, context.currency)
        self._last_result = None
        self._group_drill_category: str | None = None
        self._group_iid_to_category: dict[str, str] = {}
        self._wallet_label_to_id: dict[str, int | None] = {}

        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.period_start_var = tk.StringVar()
        self.period_end_var = tk.StringVar()
        self.category_var = tk.StringVar()
        self.tag_var = tk.StringVar()
        self.wallet_var = tk.StringVar(value=tr("reports.wallets.all", "Все кошельки"))
        self.group_var = tk.BooleanVar(value=True)
        self.totals_mode_var = tk.StringVar(value="fixed")
        self._group_status_var = tk.StringVar(value="")

        self._ui: ReportsUiHandles = build_reports_layout(self)
        self.category_combo = self._ui.category_combo
        self.wallet_menu = self._ui.wallet_menu
        self.tag_combo = self._ui.tag_combo
        self.group_status_label = self._ui.group_status_label
        self.group_back_button = self._ui.group_back_button
        self.export_button = self._ui.export_button
        self.operations_container = self._ui.operations_container
        self.operations_tree = self._ui.operations_tree
        self.monthly_tree = self._ui.monthly_tree
        self.summary_frame = self._ui.summary_frame
        self._summary_labels = self._ui.summary_labels
        self._summary_values = self._ui.summary_values

        self.operations_tree.bind("<Double-1>", self._on_operations_double_click)
        self._refresh_wallets()
        self._apply_group_ui_state()

    def _refresh_wallets(self) -> None:
        refresh_wallets(self, self._ui)

    def _current_filters(self) -> ReportFilters:
        wallet_id = self._wallet_label_to_id.get(self.wallet_var.get(), None)
        return ReportFilters(
            wallet_id=wallet_id,
            period_start=self.period_start_var.get().strip(),
            period_end=self.period_end_var.get().strip(),
            category=self.category_var.get().strip(),
            tag=self.tag_var.get().strip(),
            totals_mode=self.totals_mode_var.get().strip() or "fixed",
        )

    def _on_generate(self) -> None:
        self._refresh_wallets()
        try:
            result = self._controller.generate(self._current_filters())
        except ValueError as error:
            show_error(str(error), title=tr("common.error", "Ошибка"))
            return
        except (TypeError, RuntimeError, ValueError) as error:  # noqa: B025
            log_ui_error(logger, "UI_REPORTS_GENERATE_FAILED", error)
            show_error(
                tr("reports.error.generate", "Не удалось сформировать отчет: {error}", error=error),
                title=tr("common.error", "Ошибка"),
            )
            return

        self._last_result = result
        self._group_drill_category = None
        self._refresh_summary_only()
        self._refresh_operations_table()
        self._refresh_monthly_table()
        self._refresh_category_sources()

    def _refresh_summary_only(self) -> None:
        refresh_summary_only(self, self._ui)

    def _display_type_label(self, raw_label: str) -> str:
        normalized = str(raw_label or "").strip().lower()
        mapping = {
            "income": tr("reports.type.income", "Доход"),
            "expense": tr("reports.type.expense", "Расход"),
            "mandatory expense": tr("reports.type.mandatory", "Обязательный расход"),
            "transfer": tr("reports.type.transfer", "Перевод"),
            "доход": tr("reports.type.income", "Доход"),
            "расход": tr("reports.type.expense", "Расход"),
        }
        return mapping.get(normalized, str(raw_label or ""))

    def _display_category_label(self, raw_category: str) -> str:
        category = str(raw_category or "").strip()
        if not category or category == "<Empty>":
            return tr("reports.category.empty", "Без категории")
        return category

    def _refresh_operations_table(self) -> None:
        refresh_operations_table(self, self._ui)

    def _refresh_monthly_table(self) -> None:
        refresh_monthly_table(self, self._ui)

    def _refresh_category_sources(self) -> None:
        refresh_category_sources(self, self._ui)

    def _apply_group_ui_state(self) -> None:
        apply_group_ui_state(self, self._ui)

    def _on_group_back(self) -> None:
        if not self._group_drill_category:
            return
        self._group_drill_category = None
        self._apply_group_ui_state()

    def _on_operations_double_click(self, _event: tk.Event) -> None:
        if not self.group_var.get():
            return
        if self._group_drill_category:
            return
        selected = self.operations_tree.focus()
        if not selected:
            return
        category = self._group_iid_to_category.get(selected)
        if category is None:
            return
        self._group_drill_category = category
        self._apply_group_ui_state()

    def _apply_table_ui_state(self) -> None:
        apply_table_ui_state(self, self._ui)

    def _export(self, fmt: str) -> None:
        result = self._last_result
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

        drill_category = (self._group_drill_category or "").strip()
        export_category_only = bool(self.group_var.get()) and bool(drill_category)

        if fmt == "csv":
            filepath = filedialog.asksaveasfilename(
                defaultextension=".csv",
                filetypes=[("CSV", "*.csv")],
                title=tr("reports.export.save_csv", "Сохранить CSV"),
            )
        elif fmt == "xlsx":
            filepath = filedialog.asksaveasfilename(
                defaultextension=".xlsx",
                filetypes=[("Excel", "*.xlsx")],
                title=tr("reports.export.save_xlsx", "Сохранить XLSX"),
            )
        else:
            filepath = filedialog.asksaveasfilename(
                defaultextension=".pdf",
                filetypes=[("PDF", "*.pdf")],
                title=tr("reports.export.save_pdf", "Сохранить PDF"),
            )
        if not filepath:
            return
        try:
            base_currency = self._context.controller.get_base_currency_code()
            export_grouped_summary = bool(self.group_var.get()) and not drill_category
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
            else:
                report_to_export = (
                    result.report.filter_by_category(drill_category)
                    if export_category_only
                    else result.report
                )
                if fmt == "csv":
                    # Export report view
                    # (includes Opening/Initial balance and Total/Final balance rows)
                    report_to_csv(report_to_export, filepath, base_currency=base_currency)
                else:
                    from gui.exporters import export_report

                    export_report(
                        report_to_export,
                        filepath,
                        fmt,
                        debts=self._context.controller.get_debts(result.filters.wallet_id),
                        base_currency=base_currency,
                    )
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
                            "от текущего отображения в валюте показа.",
                        ),
                    ]
                ),
                title=tr("common.done", "Готово"),
            )
            open_in_file_manager(os.path.dirname(filepath))
        except (OSError, TypeError, ValueError, RuntimeError) as error:
            log_ui_error(logger, "UI_REPORTS_EXPORT_FAILED", error, filepath=filepath)
            show_error(
                tr("reports.export.error", "Не удалось экспортировать: {error}", error=error),
                title=tr("common.error", "Ошибка"),
            )
