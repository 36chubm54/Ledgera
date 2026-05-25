from __future__ import annotations

from collections.abc import Callable
from tkinter import ttk
from typing import Any

from gui.combobox_compat import enable_wayland_combobox_support
from gui.i18n import tr
from gui.tooltip import Tooltip


def build_reports_controls(
    owner: Any,
    *,
    on_export_menu: Callable[[ttk.Menubutton], None],
) -> tuple[
    ttk.Combobox, ttk.Combobox, ttk.Combobox, ttk.Label, ttk.Button, ttk.Button, ttk.Menubutton
]:
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
    on_export_menu(export_button)
    owner._export_tooltip = Tooltip(
        export_button,
        tr(
            "reports.export.tooltip",
            "Экспорт отчётов использует суммы в валюте базы.\n"
            "Файл может отличаться от текущего отображения в выбранной валюте показа.",
        ),
    )

    return (
        category_combo,
        wallet_menu,
        tag_combo,
        group_status_label,
        group_back_button,
        generate_button,
        export_button,
    )
