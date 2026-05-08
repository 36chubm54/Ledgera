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
from gui.record_colors import KIND_TO_FOREGROUND, foreground_for_kind
from gui.tabs.reports_controller import ReportsController
from gui.tooltip import Tooltip
from gui.ui_helpers import attach_treeview_scrollbars, show_error, show_info
from gui.ui_theme import PAD_LG, create_card_section, enable_treeview_zebra
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

        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._build_controls()
        self._build_body()
        self.operations_tree.bind("<Double-1>", self._on_operations_double_click)
        self._refresh_wallets()
        self._apply_group_ui_state()

    def _build_controls(self) -> None:
        controls = ttk.Frame(self)
        controls.grid(row=0, column=0, sticky="ew")
        controls.grid_columnconfigure(1, weight=1)
        controls.grid_columnconfigure(3, weight=1)
        controls.grid_columnconfigure(5, weight=1)
        controls.grid_columnconfigure(7, weight=1)

        self.period_start_var = tk.StringVar()
        self.period_end_var = tk.StringVar()
        self.category_var = tk.StringVar()
        self.tag_var = tk.StringVar()
        self.wallet_var = tk.StringVar(value=tr("reports.wallets.all", "Все кошельки"))
        self.group_var = tk.BooleanVar(value=True)
        self.totals_mode_var = tk.StringVar(value="fixed")

        ttk.Label(controls, text=tr("common.from", "С даты:")).grid(row=0, column=0, sticky="w")
        ttk.Entry(controls, textvariable=self.period_start_var, width=16).grid(
            row=0, column=1, sticky="ew", padx=(6, 12)
        )

        ttk.Label(controls, text=tr("common.to", "По дату:")).grid(row=0, column=2, sticky="w")
        ttk.Entry(controls, textvariable=self.period_end_var, width=16).grid(
            row=0, column=3, sticky="ew", padx=(6, 12)
        )

        ttk.Label(controls, text=tr("common.category", "Категория:")).grid(
            row=0, column=4, sticky="w"
        )
        self.category_combo = ttk.Combobox(
            controls, textvariable=self.category_var, values=[], width=18
        )
        self.category_combo.grid(row=0, column=5, sticky="ew", padx=(6, 12))

        ttk.Label(controls, text=tr("common.tags", "Теги:")).grid(row=0, column=6, sticky="w")
        self.tag_combo = ttk.Combobox(controls, textvariable=self.tag_var, values=[], width=18)
        self.tag_combo.grid(row=0, column=7, sticky="ew", padx=(6, 12))

        ttk.Label(controls, text=tr("common.wallet", "Кошелек:")).grid(row=0, column=9, sticky="w")
        self.wallet_menu = ttk.Combobox(
            controls,
            textvariable=self.wallet_var,
            values=[],
            state="readonly",
        )
        self.wallet_menu.grid(row=0, column=10, sticky="ew", padx=(6, 0))

        ttk.Checkbutton(
            controls,
            text=tr("reports.group_by_category", "Группировать по категориям"),
            variable=self.group_var,
            command=self._apply_group_ui_state,
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(8, 0))

        self._group_status_var = tk.StringVar(value="")
        self.group_status_label = ttk.Label(controls, textvariable=self._group_status_var)
        self.group_status_label.grid(
            row=1, column=2, columnspan=3, sticky="w", padx=(12, 0), pady=(8, 0)
        )

        # Hint for grouped view
        self._group_status_tooltip = Tooltip(
            self.group_status_label,
            tr(
                "reports.group_tooltip",
                "Двойной щелчок по категории открывает детализацию. "
                "Кнопка «Назад» возвращает к сводке.",
            ),
        )

        self.group_back_button = ttk.Button(
            controls,
            text=tr("common.back", "Назад"),
            command=self._on_group_back,
        )
        self.group_back_button.grid(row=1, column=5, sticky="w", padx=(12, 0), pady=(6, 0))

        totals = ttk.Frame(controls)
        totals.grid(row=1, column=6, columnspan=4, sticky="e", pady=(6, 0))
        ttk.Label(totals, text=tr("reports.totals_mode", "Режим итогов:")).grid(
            row=0, column=0, sticky="w", padx=(0, 8)
        )
        ttk.Radiobutton(
            totals,
            text=tr("reports.totals.fixed", "На историческом курсе"),
            variable=self.totals_mode_var,
            value="fixed",
            command=self._refresh_summary_only,
        ).grid(row=0, column=1, sticky="w", padx=(0, 8))
        ttk.Radiobutton(
            totals,
            text=tr("reports.totals.current", "На текущем курсе"),
            variable=self.totals_mode_var,
            value="current",
            command=self._refresh_summary_only,
        ).grid(row=0, column=2, sticky="w")

        buttons = ttk.Frame(controls)
        buttons.grid(row=2, column=0, columnspan=11, sticky="w", pady=(10, 0))
        ttk.Button(
            buttons,
            text=tr("reports.generate", "Сформировать"),
            style="Primary.TButton",
            command=self._on_generate,
        ).grid(row=0, column=0, padx=(0, 8))

        self.export_button = ttk.Menubutton(buttons, text=tr("common.export", "Экспорт"))
        self.export_button.grid(row=0, column=1, padx=(0, 8))
        export_menu = tk.Menu(self.export_button, tearoff=False)
        export_menu.add_command(label="CSV", command=lambda: self._export("csv"))
        export_menu.add_command(label="XLSX", command=lambda: self._export("xlsx"))
        export_menu.add_command(label="PDF", command=lambda: self._export("pdf"))
        self.export_button["menu"] = export_menu

    def _build_body(self) -> None:
        body = ttk.PanedWindow(self, orient=tk.HORIZONTAL, style="Reports.TPanedwindow")
        body.grid(row=1, column=0, sticky="nsew", pady=(10, 0))

        left = ttk.Frame(body)
        left.grid_rowconfigure(1, weight=1)
        left.grid_columnconfigure(0, weight=1)
        body.add(left, weight=3)

        right = ttk.Frame(body)
        right.grid_rowconfigure(0, weight=1)
        right.grid_columnconfigure(0, weight=1)
        body.add(right, weight=2)

        # (B) Summary block
        summary_card = create_card_section(left, tr("common.summary", "Сводка"))
        summary_card.grid(row=0, column=0, sticky="ew")
        self.summary_frame = summary_card.winfo_children()[-1]
        self.summary_frame.grid_columnconfigure(1, weight=1)
        self._summary_labels: dict[str, ttk.Label] = {}
        self._summary_values: dict[str, ttk.Label] = {}
        for row_index, (label_key, label_text) in enumerate(
            [
                (
                    "net_worth_fixed",
                    tr("reports.summary.net_worth_fixed", "Чистый капитал (исторический):"),
                ),
                (
                    "net_worth_current",
                    tr("reports.summary.net_worth_current", "Чистый капитал (текущий):"),
                ),
                ("initial_balance", tr("reports.summary.initial_balance", "Начальный баланс:")),
                ("records_total", tr("reports.summary.records_total", "Сумма операций:")),
                ("final_balance", tr("reports.summary.final_balance", "Итоговый баланс:")),
                ("fx_difference", tr("reports.summary.fx_difference", "Курсовая разница:")),
            ]
        ):
            label_widget = ttk.Label(self.summary_frame, text=label_text)
            label_widget.grid(row=row_index, column=0, sticky="w")
            value_label = ttk.Label(self.summary_frame, text="—")
            value_label.grid(row=row_index, column=1, sticky="e")
            self._summary_labels[label_key] = label_widget
            self._summary_values[label_key] = value_label

        # (C) Operations table
        operations_card = create_card_section(left, tr("tab.operations", "Операции"))
        operations_card.grid(row=1, column=0, sticky="nsew", pady=(PAD_LG, 0))
        self.operations_container = operations_card.winfo_children()[-1]
        self.operations_container.grid_rowconfigure(0, weight=1)
        self.operations_container.grid_columnconfigure(0, weight=1)

        self.operations_tree = ttk.Treeview(
            self.operations_container,
            columns=("date", "type", "category", "tags", "amount"),
            show="headings",
            selectmode="browse",
        )
        enable_treeview_zebra(self.operations_tree)
        self.operations_tree.heading("date", text=tr("common.date", "Дата"))
        self.operations_tree.heading("type", text=tr("common.type_short", "Тип"))
        self.operations_tree.heading("category", text=tr("common.category", "Категория"))
        self.operations_tree.heading("tags", text=tr("common.tags", "Теги"))
        self.operations_tree.heading("amount", text=tr("reports.amount_kzt", "Сумма (KZT)"))
        self.operations_tree.column("date", width=100, minwidth=100, stretch=False, anchor="w")
        self.operations_tree.column("type", width=200, minwidth=200, stretch=False, anchor="w")
        self.operations_tree.column("category", width=260, minwidth=220, stretch=False, anchor="w")
        self.operations_tree.column("tags", width=220, minwidth=160, stretch=True, anchor="w")
        self.operations_tree.column("amount", width=100, minwidth=100, anchor="e")
        self.operations_tree.grid(row=0, column=0, sticky="nsew")
        attach_treeview_scrollbars(
            self.operations_container,
            self.operations_tree,
            row=0,
            column=0,
            horizontal=False,
        )
        for kind, color in KIND_TO_FOREGROUND.items():
            try:
                self.operations_tree.tag_configure(kind, foreground=color)
            except tk.TclError:
                pass

        # (D) Monthly summary
        monthly_card = create_card_section(
            right, tr("reports.monthly_summary", "Помесячная сводка")
        )
        monthly_card.grid(row=0, column=0, sticky="nsew")
        monthly_frame = monthly_card.winfo_children()[-1]
        monthly_frame.grid_rowconfigure(0, weight=1)
        monthly_frame.grid_columnconfigure(0, weight=1)

        self.monthly_tree = ttk.Treeview(
            monthly_frame,
            columns=("month", "income", "expense"),
            show="headings",
            selectmode="none",
        )
        enable_treeview_zebra(self.monthly_tree)
        self.monthly_tree.heading("month", text=tr("common.month", "Месяц"))
        self.monthly_tree.heading("income", text=tr("analytics.income", "Доходы"))
        self.monthly_tree.heading("expense", text=tr("analytics.expenses", "Расходы"))
        self.monthly_tree.column("month", width=50, minwidth=50, anchor="w")
        self.monthly_tree.column("income", width=90, minwidth=90, anchor="e")
        self.monthly_tree.column("expense", width=90, minwidth=90, anchor="e")
        self.monthly_tree.grid(row=0, column=0, sticky="nsew")
        attach_treeview_scrollbars(
            monthly_frame,
            self.monthly_tree,
            row=0,
            column=0,
            horizontal=False,
        )

        def _block_separator_resize(event: tk.Event) -> str | None:
            if isinstance(event.widget, ttk.Treeview):
                region = event.widget.identify_region(event.x, event.y)
                if region == "separator":
                    return "break"
            return None

        def _bind_fixed_width_columns(tree: ttk.Treeview) -> None:
            tree.bind("<Button-1>", _block_separator_resize, add="+")

        _bind_fixed_width_columns(self.operations_tree)
        _bind_fixed_width_columns(self.monthly_tree)

    def _refresh_wallets(self) -> None:
        selected = self.wallet_var.get()
        all_wallets = tr("reports.wallets.all", "Все кошельки")
        self._wallet_label_to_id: dict[str, int | None] = {all_wallets: None}
        for wallet in self._controller.load_active_wallets():
            self._wallet_label_to_id[f"[{wallet.id}] {wallet.name} ({wallet.currency})"] = wallet.id
        labels = list(self._wallet_label_to_id.keys())
        selected_label = selected if selected in self._wallet_label_to_id else all_wallets
        self.wallet_menu["values"] = labels
        self.wallet_var.set(selected_label)

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
        result = self._last_result
        if result is None:
            return
        summary = result.summary
        wallet_specific = result.filters.wallet_id is not None
        self._summary_labels["net_worth_fixed"].config(
            text=(
                tr("reports.summary.wallet_balance_fixed", "Баланс кошелька (исторический):")
                if wallet_specific
                else tr("reports.summary.net_worth_fixed", "Чистый капитал (исторический):")
            )
        )
        self._summary_labels["net_worth_current"].config(
            text=(
                tr("reports.summary.wallet_balance_current", "Баланс кошелька (текущий):")
                if wallet_specific
                else tr("reports.summary.net_worth_current", "Чистый капитал (текущий):")
            )
        )
        self._summary_values["net_worth_fixed"].config(
            text=f"{_fmt_kzt(summary.net_worth_fixed)} KZT"
        )
        self._summary_values["net_worth_current"].config(
            text=f"{_fmt_kzt(summary.net_worth_current)} KZT"
        )
        self._summary_values["initial_balance"].config(
            text=f"{_fmt_kzt(summary.initial_balance)} KZT"
        )
        self._summary_values["records_total"].config(
            text=f"{_fmt_kzt(summary.records_total_fixed)} KZT"
        )
        if self.totals_mode_var.get() == "current":
            final_value = summary.final_balance_current
        else:
            final_value = summary.final_balance_fixed
        self._summary_values["final_balance"].config(text=f"{_fmt_kzt(final_value)} KZT")
        self._summary_values["fx_difference"].config(text=f"{_fmt_kzt(summary.fx_difference)} KZT")
        if summary.active_tag:
            self._group_status_var.set(
                tr("reports.filter.tag", "Фильтр по тегу: {tag}", tag=summary.active_tag)
            )
        elif not self._group_drill_category:
            self._group_status_var.set("")

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
        for iid in self.operations_tree.get_children():
            self.operations_tree.delete(iid)
        result = self._last_result
        if result is None:
            return

        if not self.group_var.get():
            for row in result.operations:
                tags = (row.kind,) if foreground_for_kind(row.kind) else ()
                self.operations_tree.insert(
                    "",
                    "end",
                    values=(
                        row.date,
                        self._display_type_label(row.type_label),
                        self._display_category_label(row.category),
                        row.tags_text,
                        f"{row.amount_kzt:.2f}",
                    ),
                    tags=tags,
                )
            return

        self._group_iid_to_category = {}
        drill_category = (self._group_drill_category or "").strip()
        if drill_category:
            for row in result.operations:
                if row.category != drill_category:
                    continue
                tags = (row.kind,) if foreground_for_kind(row.kind) else ()
                self.operations_tree.insert(
                    "",
                    "end",
                    values=(
                        row.date,
                        self._display_type_label(row.type_label),
                        self._display_category_label(row.category),
                        row.tags_text,
                        f"{row.amount_kzt:.2f}",
                    ),
                    tags=tags,
                )
            return

        for index, row in enumerate(build_category_group_rows(result.operations), start=1):
            category = self._display_category_label(row.category)
            iid = f"cat_{index}"
            self._group_iid_to_category[iid] = (
                "" if str(row.category or "").strip() == "<Empty>" else str(row.category)
            )
            self.operations_tree.insert(
                "",
                "end",
                iid=iid,
                values=(
                    "",
                    tr("reports.group.ops", "Опер.: {count}", count=row.operations_count),
                    category,
                    "",
                    f"{row.total_kzt:.2f}",
                ),
            )

    def _refresh_monthly_table(self) -> None:
        for iid in self.monthly_tree.get_children():
            self.monthly_tree.delete(iid)
        result = self._last_result
        if result is None:
            return
        for row in result.monthly:
            self.monthly_tree.insert(
                "", "end", values=(row.month, f"{row.income:.2f}", f"{row.expense:.2f}")
            )

    def _refresh_category_sources(self) -> None:
        result = self._last_result
        if result is None:
            return
        values = [""] + result.categories
        self.category_combo["values"] = values
        tag_values = [tag.name for tag in self._context.controller.list_tags()]
        self.tag_combo["values"] = [""] + tag_values

    def _apply_group_ui_state(self) -> None:
        enabled = bool(self.group_var.get())
        try:
            self.group_back_button.configure(state=("normal" if enabled else "disabled"))
        except tk.TclError:
            pass
        if not enabled:
            self._group_drill_category = None
            self._group_status_var.set("")
        else:
            self._group_status_var.set(
                tr(
                    "reports.group.category",
                    "Категория: {category}",
                    category=self._group_drill_category,
                )
                if self._group_drill_category
                else tr(
                    "reports.grouped_hint", "Сгруппированный вид (двойной щелчок по категории) ⓘ"
                )
            )
        self._refresh_operations_table()

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
        self.operations_container.grid()

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
            export_grouped_summary = bool(self.group_var.get()) and not drill_category
            if export_grouped_summary:
                from gui.exporters import export_grouped_report

                grouped_rows = [
                    (row.category, row.operations_count, row.total_kzt)
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
                    report_to_csv(report_to_export, filepath)
                else:
                    from gui.exporters import export_report

                    export_report(
                        report_to_export,
                        filepath,
                        fmt,
                        debts=self._context.controller.get_debts(result.filters.wallet_id),
                    )
            show_info(
                tr("reports.export.success", "Экспортировано в {filepath}", filepath=filepath),
                title=tr("common.done", "Готово"),
            )
            open_in_file_manager(os.path.dirname(filepath))
        except (OSError, TypeError, ValueError, RuntimeError) as error:
            log_ui_error(logger, "UI_REPORTS_EXPORT_FAILED", error, filepath=filepath)
            show_error(
                tr("reports.export.error", "Не удалось экспортировать: {error}", error=error),
                title=tr("common.error", "Ошибка"),
            )


def _fmt_kzt(value: float) -> str:
    # 1 000 000.00 style (space-grouped).
    try:
        return f"{float(value):,.2f}".replace(",", " ")
    except (TypeError, ValueError):
        return "0.00"
