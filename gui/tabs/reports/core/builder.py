"""Reports tab builder."""

from __future__ import annotations

import logging
import tkinter as tk
from tkinter import filedialog, ttk

from gui.i18n import tr
from services.analytics.report import ReportFilters
from utils.csv_utils import report_to_csv

from ..support.actions import run_export_flow, run_generate_flow
from .contracts import ReportsTabContext
from .controller import ReportsController
from .layout import ReportsUiHandles, build_reports_layout
from .render import (
    apply_group_ui_state,
    refresh_category_sources,
    refresh_monthly_table,
    refresh_operations_table,
    refresh_summary_only,
    refresh_wallets,
)

logger = logging.getLogger(__name__)


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
        self._reports_busy = False

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
        self.generate_button = self._ui.generate_button
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
        self._set_reports_busy(False)

    def _set_reports_busy(self, is_busy: bool) -> None:
        self._reports_busy = is_busy
        generate_state = tk.DISABLED if is_busy else tk.NORMAL
        export_state = tk.DISABLED if is_busy or self._last_result is None else tk.NORMAL
        self.generate_button.configure(state=generate_state)
        self.export_button.configure(state=export_state)

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
        run_generate_flow(self)

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

    def _export(self, fmt: str) -> None:
        run_export_flow(
            self,
            fmt,
            asksaveasfilename=filedialog.asksaveasfilename,
            report_to_csv=report_to_csv,
        )
