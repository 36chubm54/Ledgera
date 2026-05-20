from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from tkinter import ttk
from typing import cast

from gui.combobox_compat import (
    GuiDisplayRuntime,
    _tk_windowingsystem,
    detect_gui_display_runtime,
    enable_wayland_combobox_support,
    should_use_linux_compat_popup,
)
from gui.i18n import tr
from gui.record_colors import KIND_TO_FOREGROUND
from gui.tooltip import Tooltip
from gui.ui_helpers import attach_treeview_scrollbars, enable_treeview_column_autosize
from gui.ui_theme import PAD_LG, create_card_section, enable_treeview_zebra


@dataclass(slots=True)
class ReportsUiHandles:
    category_combo: ttk.Combobox
    wallet_menu: ttk.Combobox
    tag_combo: ttk.Combobox
    group_status_label: ttk.Label
    group_back_button: ttk.Button
    generate_button: ttk.Button
    export_button: ttk.Menubutton
    operations_container: ttk.Frame
    operations_tree: ttk.Treeview
    monthly_tree: ttk.Treeview
    summary_frame: tk.Misc
    summary_labels: dict[str, ttk.Label]
    summary_values: dict[str, ttk.Label]


class _LinuxExportPopupManager:
    def __init__(self, button: ttk.Menubutton, owner: object) -> None:
        self.button = button
        self.owner = owner
        self.popup: ttk.Frame | None = None

    def _focus_within_popup(self) -> bool:
        popup = self.popup
        if popup is None:
            return False
        widget = self.button.focus_displayof()
        if widget is None:
            return False
        return str(widget).startswith(str(popup))

    def _close_if_focus_lost(self, _event: object | None = None) -> None:
        self.button.after_idle(self._close_if_focus_still_lost)

    def _close_if_focus_still_lost(self) -> None:
        if self.popup is None:
            return
        focus_widget = self.button.focus_displayof()
        if focus_widget in (self.button, None) or self._focus_within_popup():
            return
        self.close_popup(restore_focus=False)

    def _popup_placement(self, *, height: int) -> tuple[int, int, int, int]:
        owner = cast(tk.Misc, self.button.nametowidget(str(self.button.winfo_toplevel())))
        owner.update_idletasks()
        self.button.update_idletasks()
        width = max(self.button.winfo_width(), self.button.winfo_reqwidth())
        x = self.button.winfo_rootx() - owner.winfo_rootx()
        y_below = self.button.winfo_rooty() - owner.winfo_rooty() + self.button.winfo_height()
        y_above = y_below - height - self.button.winfo_height()
        owner_height = max(owner.winfo_height(), owner.winfo_reqheight())
        y = y_below if y_below + height <= owner_height else max(0, y_above)
        owner_width = max(owner.winfo_width(), owner.winfo_reqwidth())
        x = max(0, min(x, max(0, owner_width - width)))
        return x, y, width, height

    def close_popup(self, *, restore_focus: bool = True) -> None:
        popup = self.popup
        self.popup = None
        if popup is None:
            return
        popup.place_forget()
        popup.destroy()
        if restore_focus and self.button.winfo_exists():
            self.button.focus_set()

    def _export(self, fmt: str) -> None:
        self.close_popup(restore_focus=False)
        export_method = getattr(self.owner, "_export", None)
        if callable(export_method):
            export_method(fmt)

    def open_popup(self) -> str:
        if str(self.button.cget("state")) == str(tk.DISABLED):
            return "break"
        if self.popup is not None:
            self.close_popup()
            return "break"

        owner = cast(tk.Misc, self.button.nametowidget(str(self.button.winfo_toplevel())))
        popup = ttk.Frame(owner, padding=1, style="Card.TFrame")
        popup.grid_columnconfigure(0, weight=1)

        entries = (
            ("CSV", "csv"),
            ("XLSX", "xlsx"),
            ("PDF", "pdf"),
        )
        first_button: ttk.Button | None = None
        for row_index, (label, fmt) in enumerate(entries):
            option_button = ttk.Button(
                popup,
                text=label,
                command=lambda selected=fmt: self._export(selected),
            )
            option_button.grid(row=row_index, column=0, sticky="ew")
            option_button.bind(
                "<Escape>",
                lambda _event: (self.close_popup(), "break")[1],
                add="+",
            )
            option_button.bind("<FocusOut>", self._close_if_focus_lost, add="+")
            if first_button is None:
                first_button = option_button

        self.popup = popup
        popup.update_idletasks()
        pos_x, pos_y, width, height = self._popup_placement(height=popup.winfo_reqheight())
        popup.place(x=pos_x, y=pos_y, width=width, height=height)
        popup.lift()
        popup.bind("<FocusOut>", self._close_if_focus_lost, add="+")
        popup.bind("<Escape>", lambda _event: (self.close_popup(), "break")[1], add="+")
        if first_button is not None:
            popup.after(0, first_button.focus_set)
        return "break"

    def bind(self) -> None:
        self.button.bind("<Button-1>", lambda _event: self.open_popup(), add="+")
        self.button.bind("<Return>", lambda _event: self.open_popup(), add="+")
        self.button.bind("<KP_Enter>", lambda _event: self.open_popup(), add="+")
        self.button.bind("<space>", lambda _event: self.open_popup(), add="+")
        self.button.bind("<Down>", lambda _event: self.open_popup(), add="+")
        self.button.bind("<Alt-Down>", lambda _event: self.open_popup(), add="+")
        self.button.bind("<Escape>", lambda _event: (self.close_popup(), "break")[1], add="+")


def _should_use_linux_export_popup(runtime: GuiDisplayRuntime, widget: tk.Misc) -> bool:
    return should_use_linux_compat_popup(
        runtime,
        tk_windowingsystem=_tk_windowingsystem(widget),
    )


def build_reports_layout(owner) -> ReportsUiHandles:
    controls = ttk.Frame(owner)
    controls.grid(row=0, column=0, sticky="ew")
    controls.grid_columnconfigure(0, weight=1)

    top_filters = ttk.Frame(controls)
    top_filters.grid(row=0, column=0, sticky="ew")
    for column in (1, 3, 5, 7):
        top_filters.grid_columnconfigure(column, weight=1, uniform="reports_filters")

    ttk.Label(top_filters, text=tr("common.from", "С даты:")).grid(row=0, column=0, sticky="w")
    ttk.Entry(top_filters, textvariable=owner.period_start_var, width=16).grid(
        row=0, column=1, sticky="ew", padx=(6, 16)
    )

    ttk.Label(top_filters, text=tr("common.to", "По дату:")).grid(row=0, column=2, sticky="w")
    ttk.Entry(top_filters, textvariable=owner.period_end_var, width=16).grid(
        row=0, column=3, sticky="ew", padx=(6, 16)
    )

    ttk.Label(top_filters, text=tr("common.category", "Категория:")).grid(
        row=0, column=4, sticky="w"
    )
    category_combo = ttk.Combobox(top_filters, textvariable=owner.category_var, values=[], width=18)
    category_combo.grid(row=0, column=5, sticky="ew", padx=(6, 16))
    enable_wayland_combobox_support(category_combo)

    ttk.Label(top_filters, text=tr("common.wallet", "Кошелек:")).grid(row=0, column=6, sticky="w")
    wallet_menu = ttk.Combobox(
        top_filters,
        textvariable=owner.wallet_var,
        values=[],
        state="readonly",
    )
    wallet_menu.grid(row=0, column=7, sticky="ew", padx=(6, 0))
    enable_wayland_combobox_support(wallet_menu)

    middle_row = ttk.Frame(controls)
    middle_row.grid(row=1, column=0, sticky="ew", pady=(8, 0))
    middle_row.grid_columnconfigure(0, weight=3)
    middle_row.grid_columnconfigure(1, weight=2)
    middle_row.grid_columnconfigure(2, weight=3)

    tag_filters = ttk.Frame(middle_row)
    tag_filters.grid(row=0, column=0, sticky="ew")
    tag_filters.grid_columnconfigure(1, weight=1)
    ttk.Label(tag_filters, text=tr("common.tags", "Теги:")).grid(row=0, column=0, sticky="w")
    tag_combo = ttk.Combobox(tag_filters, textvariable=owner.tag_var, values=[], width=18)
    tag_combo.grid(row=0, column=1, sticky="ew", padx=(6, 0))
    enable_wayland_combobox_support(tag_combo)

    group_frame = ttk.Frame(middle_row)
    group_frame.grid(row=0, column=1, sticky="ew", padx=(16, 16))
    group_frame.grid_columnconfigure(1, weight=1)
    ttk.Checkbutton(
        group_frame,
        text=tr("reports.group_by_category", "Группировать по категориям"),
        variable=owner.group_var,
        command=owner._apply_group_ui_state,
    ).grid(row=0, column=0, sticky="w")

    group_status_label = ttk.Label(group_frame, textvariable=owner._group_status_var)
    group_status_label.grid(row=0, column=1, sticky="w", padx=(12, 0))
    owner._group_status_tooltip = Tooltip(
        group_status_label,
        tr(
            "reports.group_tooltip",
            "Двойной щелчок по категории открывает детализацию. "
            "Кнопка «Назад» возвращает к сводке.",
        ),
    )

    group_back_button = ttk.Button(
        group_frame,
        text=tr("common.back", "Назад"),
        command=owner._on_group_back,
    )
    group_back_button.grid(row=0, column=2, sticky="w", padx=(12, 0))

    totals = ttk.Frame(middle_row)
    totals.grid(row=0, column=2, sticky="e")
    ttk.Label(totals, text=tr("reports.totals_mode", "Режим итогов:")).grid(
        row=0, column=0, sticky="w", padx=(0, 8)
    )
    ttk.Radiobutton(
        totals,
        text=tr("reports.totals.fixed", "На историческом курсе"),
        variable=owner.totals_mode_var,
        value="fixed",
        command=owner._refresh_summary_only,
    ).grid(row=0, column=1, sticky="w", padx=(0, 8))
    ttk.Radiobutton(
        totals,
        text=tr("reports.totals.current", "На текущем курсе"),
        variable=owner.totals_mode_var,
        value="current",
        command=owner._refresh_summary_only,
    ).grid(row=0, column=2, sticky="w")

    buttons = ttk.Frame(controls)
    buttons.grid(row=2, column=0, sticky="w", pady=(10, 0))
    generate_button = ttk.Button(
        buttons,
        text=tr("reports.generate", "Сформировать"),
        style="Primary.TButton",
        command=owner._on_generate,
    )
    generate_button.grid(row=0, column=0, padx=(0, 8))

    export_button = ttk.Menubutton(buttons, text=tr("common.export", "Экспорт"))
    export_button.grid(row=0, column=1, padx=(0, 8))
    runtime = detect_gui_display_runtime()
    if _should_use_linux_export_popup(runtime, export_button):
        export_popup_manager = _LinuxExportPopupManager(export_button, owner)
        export_popup_manager.bind()
        setattr(export_button, "_linux_export_popup_manager", export_popup_manager)  # noqa: B010
    else:
        export_menu = tk.Menu(export_button, tearoff=False)
        export_menu.add_command(label="CSV", command=lambda: owner._export("csv"))
        export_menu.add_command(label="XLSX", command=lambda: owner._export("xlsx"))
        export_menu.add_command(label="PDF", command=lambda: owner._export("pdf"))
        export_button["menu"] = export_menu
    owner._export_tooltip = Tooltip(
        export_button,
        tr(
            "reports.export.tooltip",
            "Экспорт отчётов использует суммы в валюте базы.\n"
            "Файл может отличаться от текущего отображения в выбранной валюте показа.",
        ),
    )

    body = ttk.PanedWindow(owner, orient=tk.HORIZONTAL, style="Reports.TPanedwindow")
    body.grid(row=1, column=0, sticky="nsew", pady=(10, 0))

    left = ttk.Frame(body)
    left.grid_rowconfigure(1, weight=1)
    left.grid_columnconfigure(0, weight=1)
    body.add(left, weight=3)

    right = ttk.Frame(body)
    right.grid_rowconfigure(0, weight=1)
    right.grid_columnconfigure(0, weight=1)
    body.add(right, weight=2)

    summary_card = create_card_section(left, tr("common.summary", "Сводка"))
    summary_card.grid(row=0, column=0, sticky="ew")
    summary_frame = summary_card.winfo_children()[-1]
    summary_frame.grid_columnconfigure(1, weight=1)
    summary_labels: dict[str, ttk.Label] = {}
    summary_values: dict[str, ttk.Label] = {}
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
        label_widget = ttk.Label(summary_frame, text=label_text, style="CardText.TLabel")
        label_widget.grid(row=row_index, column=0, sticky="w")
        value_label = ttk.Label(summary_frame, text="—", style="CardText.TLabel")
        value_label.grid(row=row_index, column=1, sticky="e")
        summary_labels[label_key] = label_widget
        summary_values[label_key] = value_label

    operations_card = create_card_section(left, tr("tab.operations", "Операции"))
    operations_card.grid(row=1, column=0, sticky="nsew", pady=(PAD_LG, 0))
    operations_container = cast(ttk.Frame, operations_card.winfo_children()[-1])
    operations_container.grid_rowconfigure(0, weight=1)
    operations_container.grid_columnconfigure(0, weight=1)

    operations_tree = ttk.Treeview(
        operations_container,
        columns=("date", "type", "category", "tags", "amount"),
        show="headings",
        selectmode="browse",
    )
    enable_treeview_zebra(operations_tree)
    operations_tree.heading("date", text=tr("common.date_short", "Дата"))
    operations_tree.heading("type", text=tr("common.type_short", "Тип"))
    operations_tree.heading("category", text=tr("common.category_short", "Категория"))
    operations_tree.heading("tags", text=tr("common.tags_short", "Теги"))
    operations_tree.heading("amount", text=tr("common.amount_short", "Сумма"))
    operations_tree.column("date", width=100, minwidth=100, stretch=False, anchor="w")
    operations_tree.column("type", width=200, minwidth=200, stretch=False, anchor="w")
    operations_tree.column("category", width=260, minwidth=220, stretch=False, anchor="w")
    operations_tree.column("tags", width=220, minwidth=160, stretch=True, anchor="w")
    operations_tree.column("amount", width=100, minwidth=100, anchor="e")
    enable_treeview_column_autosize(
        operations_tree,
        columns=("category", "tags"),
        max_width=420,
    )
    operations_tree.grid(row=0, column=0, sticky="nsew")
    attach_treeview_scrollbars(
        operations_container,
        operations_tree,
        row=0,
        column=0,
        horizontal=False,
    )
    for kind, color in KIND_TO_FOREGROUND.items():
        try:
            operations_tree.tag_configure(kind, foreground=color)
        except tk.TclError:
            pass

    monthly_card = create_card_section(
        right,
        tr("reports.monthly_summary", "Помесячная сводка"),
        body_padding=(4, 4, 4, 4),
    )
    monthly_card.grid(row=0, column=0, sticky="nsew")
    monthly_frame = monthly_card.winfo_children()[-1]
    monthly_frame.grid_rowconfigure(0, weight=1)
    monthly_frame.grid_columnconfigure(0, weight=1)

    monthly_tree = ttk.Treeview(
        monthly_frame,
        columns=("month", "income", "expense"),
        show="headings",
        selectmode="none",
        height=12,
    )
    enable_treeview_zebra(monthly_tree)
    monthly_tree.heading("month", text=tr("common.month", "Месяц"))
    monthly_tree.heading("income", text=tr("reports.income", "Доход"))
    monthly_tree.heading("expense", text=tr("reports.expense", "Расход"))
    monthly_tree.column("month", width=50, minwidth=50, anchor="w")
    monthly_tree.column("income", width=90, minwidth=90, anchor="e")
    monthly_tree.column("expense", width=90, minwidth=90, anchor="e")
    monthly_tree.grid(row=0, column=0, sticky="nsew")
    attach_treeview_scrollbars(
        monthly_frame,
        monthly_tree,
        row=0,
        column=0,
        horizontal=False,
        padx=0,
        pady=0,
    )

    def _block_separator_resize(event: tk.Event) -> str | None:
        if isinstance(event.widget, ttk.Treeview):
            region = event.widget.identify_region(event.x, event.y)
            if region == "separator":
                return "break"
        return None

    def _bind_fixed_width_columns(tree: ttk.Treeview) -> None:
        tree.bind("<Button-1>", _block_separator_resize, add="+")

    _bind_fixed_width_columns(operations_tree)
    _bind_fixed_width_columns(monthly_tree)

    return ReportsUiHandles(
        category_combo=category_combo,
        wallet_menu=wallet_menu,
        tag_combo=tag_combo,
        group_status_label=group_status_label,
        group_back_button=group_back_button,
        generate_button=generate_button,
        export_button=export_button,
        operations_container=operations_container,
        operations_tree=operations_tree,
        monthly_tree=monthly_tree,
        summary_frame=summary_frame,
        summary_labels=summary_labels,
        summary_values=summary_values,
    )
