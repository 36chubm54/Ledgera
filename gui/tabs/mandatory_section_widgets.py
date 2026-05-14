from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass
from tkinter import ttk
from typing import Any, cast

from gui.i18n import tr
from gui.ui_helpers import enable_treeview_column_autosize
from gui.ui_theme import PAD_SM, PAD_XS, enable_treeview_zebra

FORM_LABEL_WIDTH = 20


@dataclass(slots=True)
class MandatoryAddFormFields:
    panel: ttk.Frame
    amount_entry: ttk.Entry
    currency_entry: ttk.Entry
    wallet_var: tk.StringVar
    wallet_menu: ttk.Combobox
    wallet_map: dict[str, int]
    category_entry: ttk.Entry
    description_entry: ttk.Entry
    period_var: tk.StringVar
    period_combo: ttk.Combobox
    date_entry: ttk.Entry


@dataclass(slots=True)
class MandatoryEditFormFields:
    panel: ttk.Frame
    amount_base_entry: ttk.Entry
    wallet_var: tk.StringVar
    wallet_menu: ttk.Combobox
    wallet_map: dict[str, int]
    period_var: tk.StringVar
    period_combo: ttk.Combobox
    date_entry: ttk.Entry


@dataclass(slots=True)
class MandatoryAddToRecordsFields:
    panel: ttk.Frame
    wallet_var: tk.StringVar
    wallet_menu: ttk.Combobox
    wallet_map: dict[str, int]
    date_entry: ttk.Entry


@dataclass(slots=True)
class InlineActionButtons:
    save_button: ttk.Button
    cancel_button: ttk.Button


def _configure_panel_grid(panel: ttk.Frame, *, stacked: bool = False) -> None:
    if stacked:
        panel.grid_columnconfigure(0, weight=1)
        panel.grid_columnconfigure(1, weight=0, minsize=0)
        return
    panel.grid_columnconfigure(0, weight=0)
    panel.grid_columnconfigure(1, weight=1, minsize=160)


def _create_form_panel(
    parent: tk.Misc,
    *,
    row_index: int,
    inline: bool,
) -> ttk.Frame:
    if inline:
        panel = ttk.Frame(parent, style="InlinePanel.TFrame", padding=(PAD_SM, PAD_XS))
    else:
        panel = ttk.Frame(parent, style="CardBody.TFrame", padding=(PAD_SM, PAD_XS))
    panel.grid(row=row_index, column=0, pady=PAD_SM, sticky="ew")
    _configure_panel_grid(panel, stacked=not inline)
    return panel


def _create_inline_panel(parent: tk.Misc) -> ttk.Frame:
    return _create_form_panel(parent, row_index=0, inline=True)


def _wallet_map(controller: Any) -> dict[str, int]:
    return {
        f"[{wallet.id}] {wallet.name} ({wallet.currency})": wallet.id
        for wallet in controller.load_active_wallets()
    }


def refresh_add_form_wallets(form: MandatoryAddFormFields, controller: Any) -> None:
    wallet_map = _wallet_map(controller)
    wallet_labels = list(wallet_map.keys()) or [""]
    form.wallet_map.clear()
    form.wallet_map.update(wallet_map)
    form.wallet_menu["values"] = wallet_labels
    if form.wallet_var.get() not in form.wallet_map:
        form.wallet_var.set(wallet_labels[0])


def _build_wallet_selector(
    panel: ttk.Frame,
    *,
    row_index: int,
    controller: Any,
    selected_wallet_id: int | None = None,
    stacked: bool = False,
    label_style: str = "FormField.TLabel",
) -> tuple[tk.StringVar, ttk.Combobox, dict[str, int]]:
    wallet_label = ttk.Label(
        panel,
        text=tr("common.wallet", "Кошелек:"),
        width=FORM_LABEL_WIDTH,
        anchor="w",
        style=label_style,
    )
    wallet_label.grid(
        row=row_index,
        column=0,
        sticky="w",
        columnspan=2 if stacked else 1,
        padx=PAD_SM,
        pady=PAD_XS,
    )
    wallet_var = tk.StringVar(value="")
    wallet_menu = ttk.Combobox(
        panel,
        textvariable=wallet_var,
        values=[],
        state="readonly",
    )
    if stacked:
        wallet_menu.grid(
            row=row_index + 1,
            column=0,
            sticky="ew",
            padx=PAD_SM,
            pady=(0, PAD_XS),
        )
    else:
        wallet_menu.grid(row=row_index, column=1, sticky="ew", padx=PAD_SM, pady=PAD_XS)
    wallet_map = _wallet_map(controller)
    wallet_labels = list(wallet_map.keys()) or [""]
    wallet_menu["values"] = wallet_labels
    if selected_wallet_id is None:
        wallet_var.set(wallet_labels[0])
    else:
        current_wallet_label = next(
            (
                label
                for label, wallet_id in wallet_map.items()
                if int(wallet_id) == int(selected_wallet_id)
            ),
            wallet_labels[0],
        )
        wallet_var.set(current_wallet_label)
    return wallet_var, wallet_menu, wallet_map


def _place_field(
    *,
    stacked: bool,
    label: ttk.Label,
    widget: Any,
    row: int,
) -> int:
    if stacked:
        label.grid(row=row, column=0, sticky="w", padx=PAD_SM, pady=PAD_XS)
        widget.grid(row=row + 1, column=0, sticky="ew", padx=PAD_SM, pady=(0, PAD_XS))
        return row + 2
    label.grid(row=row, column=0, sticky="w", padx=PAD_SM, pady=PAD_XS)
    widget.grid(row=row, column=1, sticky="ew", padx=PAD_SM, pady=PAD_XS)
    return row + 1


def _grid_inline_field(
    panel: ttk.Frame,
    *,
    row_index: int,
    text: str,
    widget: Any,
) -> None:
    ttk.Label(
        panel,
        text=text,
        width=FORM_LABEL_WIDTH,
        anchor="w",
        style="InlineField.TLabel",
    ).grid(
        row=row_index,
        column=0,
        sticky="w",
        padx=PAD_SM,
        pady=PAD_XS,
    )
    widget.grid(
        row=row_index,
        column=1,
        sticky="ew",
        padx=PAD_SM,
        pady=PAD_XS,
    )


def build_add_mandatory_panel(
    parent: tk.Misc,
    *,
    controller: Any,
    base_currency_code: str,
    row_index: int = 3,
    inline: bool = True,
) -> MandatoryAddFormFields:
    panel = _create_form_panel(parent, row_index=row_index, inline=inline)
    if not inline:
        panel.grid_columnconfigure(1, weight=1)
        panel.grid_columnconfigure(2, weight=1)
        panel.grid_columnconfigure(3, weight=0)

        def form_label(row: int, text: str) -> ttk.Label:
            label = ttk.Label(
                panel,
                text=text,
                width=FORM_LABEL_WIDTH,
                anchor="w",
                style="FormField.TLabel",
            )
            label.grid(row=row, column=0, sticky="w", padx=PAD_SM, pady=PAD_XS)
            return label

        form_label(0, tr("mandatory.field.amount", "Сумма"))
        amount_entry = ttk.Entry(panel)
        amount_entry.grid(row=0, column=1, columnspan=3, sticky="ew", padx=PAD_SM, pady=PAD_XS)

        form_label(1, tr("mandatory.field.currency", "Валюта"))
        currency_entry = ttk.Entry(panel)
        currency_entry.insert(0, base_currency_code)
        currency_entry.grid(
            row=1,
            column=1,
            columnspan=3,
            sticky="ew",
            padx=PAD_SM,
            pady=PAD_XS,
        )

        form_label(2, tr("common.wallet", "Кошелек:"))
        wallet_var = tk.StringVar(value="")
        wallet_menu = ttk.Combobox(
            panel,
            textvariable=wallet_var,
            values=[],
            state="readonly",
        )
        wallet_map = _wallet_map(controller)
        wallet_labels = list(wallet_map.keys()) or [""]
        wallet_menu["values"] = wallet_labels
        wallet_var.set(wallet_labels[0])
        wallet_menu.grid(
            row=2,
            column=1,
            columnspan=3,
            sticky="ew",
            padx=PAD_SM,
            pady=PAD_XS,
        )

        form_label(3, tr("mandatory.field.category", "Категория"))
        category_entry = ttk.Entry(panel)
        category_entry.insert(0, "Mandatory")
        category_entry.grid(
            row=3,
            column=1,
            columnspan=3,
            sticky="ew",
            padx=PAD_SM,
            pady=PAD_XS,
        )

        form_label(4, tr("common.description", "Описание:"))
        description_entry = ttk.Entry(panel)
        description_entry.grid(
            row=4,
            column=1,
            columnspan=3,
            sticky="ew",
            padx=PAD_SM,
            pady=PAD_XS,
        )

        form_label(5, tr("common.period", "Период:"))
        period_var = tk.StringVar(value="monthly")
        period_combo = ttk.Combobox(
            panel,
            textvariable=period_var,
            values=["daily", "weekly", "monthly", "yearly"],
            state="readonly",
        )
        period_combo.grid(
            row=5,
            column=1,
            columnspan=3,
            sticky="ew",
            padx=PAD_SM,
            pady=PAD_XS,
        )

        form_label(6, tr("mandatory.field.date_optional", "Дата (необязательно):"))
        date_entry = ttk.Entry(panel)
        date_entry.grid(row=6, column=1, columnspan=3, sticky="ew", padx=PAD_SM, pady=PAD_XS)

        return MandatoryAddFormFields(
            panel=panel,
            amount_entry=amount_entry,
            currency_entry=currency_entry,
            wallet_var=wallet_var,
            wallet_menu=wallet_menu,
            wallet_map=wallet_map,
            category_entry=category_entry,
            description_entry=description_entry,
            period_var=period_var,
            period_combo=period_combo,
            date_entry=date_entry,
        )

    stacked = True

    current_row = 0
    amount_label = ttk.Label(
        panel,
        text=tr("mandatory.field.amount", "Сумма"),
        width=FORM_LABEL_WIDTH,
        anchor="w",
        style="InlineField.TLabel",
    )
    amount_entry = ttk.Entry(panel)
    current_row = _place_field(
        stacked=stacked,
        label=amount_label,
        widget=amount_entry,
        row=current_row,
    )

    currency_label = ttk.Label(
        panel,
        text=tr("mandatory.field.currency", "Валюта:"),
        width=FORM_LABEL_WIDTH,
        anchor="w",
        style="InlineField.TLabel",
    )
    currency_entry = ttk.Entry(panel)
    currency_entry.insert(0, base_currency_code)
    current_row = _place_field(
        stacked=stacked,
        label=currency_label,
        widget=currency_entry,
        row=current_row,
    )

    wallet_var, wallet_menu, wallet_map = _build_wallet_selector(
        panel,
        row_index=current_row,
        controller=controller,
        stacked=stacked,
        label_style="InlineField.TLabel",
    )
    current_row += 2 if stacked else 1

    category_label = ttk.Label(
        panel,
        text=tr("mandatory.field.category", "Категория"),
        width=FORM_LABEL_WIDTH,
        anchor="w",
        style="InlineField.TLabel",
    )
    category_entry = ttk.Entry(panel)
    category_entry.insert(0, "Mandatory")
    current_row = _place_field(
        stacked=stacked,
        label=category_label,
        widget=category_entry,
        row=current_row,
    )

    description_label = ttk.Label(
        panel,
        text=tr("common.description", "Описание:"),
        width=FORM_LABEL_WIDTH,
        anchor="w",
        style="InlineField.TLabel",
    )
    description_entry = ttk.Entry(panel)
    current_row = _place_field(
        stacked=stacked,
        label=description_label,
        widget=description_entry,
        row=current_row,
    )

    period_label = ttk.Label(
        panel,
        text=tr("common.period", "Период:"),
        width=FORM_LABEL_WIDTH,
        anchor="w",
        style="InlineField.TLabel",
    )
    period_var = tk.StringVar(value="monthly")
    period_combo = ttk.Combobox(
        panel,
        textvariable=period_var,
        values=["daily", "weekly", "monthly", "yearly"],
        state="readonly",
    )
    current_row = _place_field(
        stacked=stacked,
        label=period_label,
        widget=period_combo,
        row=current_row,
    )

    date_label = ttk.Label(
        panel,
        text=tr("mandatory.field.date_optional", "Дата (необязательно):"),
        width=FORM_LABEL_WIDTH,
        anchor="w",
        style="InlineField.TLabel",
    )
    date_entry = ttk.Entry(panel)
    _place_field(
        stacked=stacked,
        label=date_label,
        widget=date_entry,
        row=current_row,
    )

    return MandatoryAddFormFields(
        panel=panel,
        amount_entry=amount_entry,
        currency_entry=currency_entry,
        wallet_var=wallet_var,
        wallet_menu=wallet_menu,
        wallet_map=wallet_map,
        category_entry=category_entry,
        description_entry=description_entry,
        period_var=period_var,
        period_combo=period_combo,
        date_entry=date_entry,
    )


def build_edit_mandatory_panel(
    parent: tk.Misc,
    *,
    controller: Any,
    expense: Any,
) -> MandatoryEditFormFields:
    panel = _create_inline_panel(parent)

    amount_base_entry = ttk.Entry(panel)
    amount_base_entry.insert(0, str(expense.amount_base))
    _grid_inline_field(
        panel,
        row_index=0,
        text=tr("mandatory.field.amount_base", "Сумма в валюте базы:"),
        widget=amount_base_entry,
    )

    wallet_var, wallet_menu, wallet_map = _build_wallet_selector(
        panel,
        row_index=1,
        controller=controller,
        selected_wallet_id=int(expense.wallet_id),
        label_style="InlineField.TLabel",
    )

    period_var = tk.StringVar(value=str(expense.period or "monthly"))
    period_combo = ttk.Combobox(
        panel,
        textvariable=period_var,
        values=["daily", "weekly", "monthly", "yearly"],
        state="readonly",
    )
    _grid_inline_field(
        panel,
        row_index=2,
        text=tr("common.period", "Период:"),
        widget=period_combo,
    )

    date_entry = ttk.Entry(panel)
    date_entry.insert(0, mandatory_date_text(expense))
    _grid_inline_field(
        panel,
        row_index=3,
        text=tr("mandatory.field.date_optional", "Дата (необязательно):"),
        widget=date_entry,
    )

    return MandatoryEditFormFields(
        panel=panel,
        amount_base_entry=amount_base_entry,
        wallet_var=wallet_var,
        wallet_menu=wallet_menu,
        wallet_map=wallet_map,
        period_var=period_var,
        period_combo=period_combo,
        date_entry=date_entry,
    )


def build_add_to_records_panel(
    parent: tk.Misc,
    *,
    controller: Any,
) -> MandatoryAddToRecordsFields:
    panel = _create_inline_panel(parent)

    date_entry = ttk.Entry(panel)
    _grid_inline_field(
        panel,
        row_index=0,
        text=tr("mandatory.field.date_required", "Дата (YYYY-MM-DD):"),
        widget=date_entry,
    )

    wallet_var, wallet_menu, wallet_map = _build_wallet_selector(
        panel,
        row_index=1,
        controller=controller,
        label_style="InlineField.TLabel",
    )
    return MandatoryAddToRecordsFields(
        panel=panel,
        wallet_var=wallet_var,
        wallet_menu=wallet_menu,
        wallet_map=wallet_map,
        date_entry=date_entry,
    )


def next_grid_row(parent: tk.Misc) -> int:
    rows = []
    for child in parent.winfo_children():
        grid_info = getattr(child, "grid_info", None)
        if not callable(grid_info):
            continue
        info = cast(dict[str, Any], grid_info())
        if "row" in info:
            rows.append(int(info["row"]))
    return max(rows, default=-1) + 1


def bind_focus_navigation(
    widgets: list[tk.Misc],
    *,
    submit_action: Callable[[], None] | None = None,
    cancel_action: Callable[[], None] | None = None,
) -> None:
    def _focus_relative(index: int) -> str:
        widgets[index % len(widgets)].focus_set()
        return "break"

    for index, widget in enumerate(widgets):
        widget.bind("<Up>", lambda _event, i=index - 1: _focus_relative(i), add="+")
        widget.bind("<Down>", lambda _event, i=index + 1: _focus_relative(i), add="+")
        if isinstance(widget, ttk.Button):
            widget.bind("<Left>", lambda _event, i=index - 1: _focus_relative(i), add="+")
            widget.bind("<Right>", lambda _event, i=index + 1: _focus_relative(i), add="+")
            widget.bind("<Return>", lambda _event: (_event.widget.invoke(), "break")[1], add="+")
            widget.bind("<KP_Enter>", lambda _event: (_event.widget.invoke(), "break")[1], add="+")
        elif callable(submit_action):
            widget.bind("<Return>", lambda _event: (submit_action(), "break")[1], add="+")
            widget.bind("<KP_Enter>", lambda _event: (submit_action(), "break")[1], add="+")

        if callable(cancel_action):
            widget.bind("<Escape>", lambda _event: (cancel_action(), "break")[1], add="+")


def build_inline_action_buttons(
    panel: ttk.Frame,
    *,
    row_index: int,
    on_save: Callable[[], None],
    on_cancel: Callable[[], None],
) -> InlineActionButtons:
    buttons = ttk.Frame(panel, style="InlinePanel.TFrame")
    buttons.grid(row=row_index, column=0, columnspan=2, sticky="ew", pady=(8, 0))
    buttons.grid_columnconfigure(0, weight=1)
    buttons.grid_columnconfigure(1, weight=1)
    save_button = ttk.Button(
        buttons,
        text=tr("common.save", "Сохранить"),
        style="Primary.TButton",
        command=on_save,
    )
    save_button.grid(row=0, column=0, sticky="ew", padx=(0, 6))
    cancel_button = ttk.Button(
        buttons,
        text=tr("common.cancel", "Отмена"),
        command=on_cancel,
    )
    cancel_button.grid(row=0, column=1, sticky="ew", padx=(6, 0))
    return InlineActionButtons(
        save_button=save_button,
        cancel_button=cancel_button,
    )


def build_mandatory_actions_row(
    parent: tk.Misc,
    *,
    format_var: tk.StringVar,
    on_edit: Callable[[], None],
    on_add_to_records: Callable[[], None],
    on_delete: Callable[[], None],
    on_delete_all: Callable[[], None],
    on_refresh: Callable[[], None],
    on_import: Callable[[], None],
    on_export: Callable[[], None],
    pad_x: int,
    pad_y: int,
    row_index: int = 3,
) -> None:
    actions = ttk.Frame(parent)
    actions.grid(
        row=row_index,
        column=0,
        columnspan=2,
        sticky="ew",
        padx=pad_x,
        pady=(PAD_SM, pad_y),
    )
    for idx in range(4):
        actions.grid_columnconfigure(idx, weight=1)

    ttk.Button(actions, text=tr("common.edit", "Редактировать"), command=on_edit).grid(
        row=0, column=0, sticky="ew", padx=(0, 6), pady=(0, 6)
    )
    ttk.Button(
        actions,
        text=tr("mandatory.add_to_records", "Добавить в записи"),
        command=on_add_to_records,
    ).grid(row=0, column=1, sticky="ew", padx=6, pady=(0, 6))
    ttk.Button(actions, text=tr("common.delete", "Удалить"), command=on_delete).grid(
        row=0, column=2, sticky="ew", padx=6, pady=(0, 6)
    )
    ttk.Button(
        actions,
        text=tr("mandatory.delete_all", "Удалить все"),
        command=on_delete_all,
    ).grid(row=0, column=3, sticky="ew", padx=(6, 0), pady=(0, 6))
    ttk.Button(actions, text=tr("common.refresh", "Обновить"), command=on_refresh).grid(
        row=1, column=0, sticky="ew", padx=(0, 6)
    )
    ttk.Combobox(
        actions,
        textvariable=format_var,
        values=["CSV", "XLSX"],
        state="readonly",
    ).grid(row=1, column=1, sticky="ew", padx=6)
    ttk.Button(actions, text=tr("common.import", "Импорт"), command=on_import).grid(
        row=1, column=2, sticky="ew", padx=6
    )
    ttk.Button(actions, text=tr("common.export", "Экспорт"), command=on_export).grid(
        row=1, column=3, sticky="ew", padx=(6, 0)
    )


def build_mandatory_tree(parent: tk.Misc) -> tuple[ttk.Treeview, ttk.Scrollbar, ttk.Scrollbar]:
    mand_tree = ttk.Treeview(
        parent,
        show="headings",
        selectmode="browse",
        columns=(
            "index",
            "amount",
            "currency",
            "kzt",
            "category",
            "description",
            "period",
            "date",
            "autopay",
        ),
    )
    enable_treeview_zebra(mand_tree)
    for col, text, width, minwidth, stretch, anchor in (
        ("index", "#", 40, 40, False, "e"),
        ("amount", tr("mandatory.amount", "Сумма"), 90, 90, False, "e"),
        ("currency", tr("mandatory.currency_short", "Вал."), 60, 60, False, "center"),
        ("kzt", "KZT", 90, 90, False, "e"),
        ("category", tr("mandatory.category", "Категория"), 120, 120, False, "w"),
        ("description", tr("mandatory.description", "Описание"), 200, 160, True, "w"),
        ("period", tr("mandatory.period", "Период"), 90, 80, False, "w"),
        ("date", tr("mandatory.date", "Дата"), 100, 100, False, "w"),
        ("autopay", tr("mandatory.autopay", "Автоплатеж"), 120, 100, False, "center"),
    ):
        mand_tree.heading(col, text=text)
        mand_tree.column(col, width=width, minwidth=minwidth, stretch=stretch, anchor=anchor)  # type: ignore[arg-type]
    enable_treeview_column_autosize(
        mand_tree,
        columns=("category", "description"),
        max_width=360,
    )
    mand_tree.grid(row=0, column=0, sticky="nsew", padx=PAD_SM, pady=PAD_SM)

    mand_yscroll = ttk.Scrollbar(parent, orient="vertical", command=mand_tree.yview)
    mand_yscroll.grid(row=0, column=1, sticky="ns", pady=PAD_SM)
    mand_tree.configure(yscrollcommand=mand_yscroll.set)

    mand_xscroll = ttk.Scrollbar(parent, orient="horizontal", command=mand_tree.xview)
    mand_xscroll.grid(row=1, column=0, sticky="ew", padx=PAD_SM, pady=(0, PAD_SM))
    mand_tree.configure(xscrollcommand=mand_xscroll.set)

    return mand_tree, mand_yscroll, mand_xscroll


def bind_mandatory_horizontal_scroll(
    mand_tree: ttk.Treeview,
    mand_xscroll: ttk.Scrollbar | None,
) -> None:
    def _mandatory_scroll_units(delta: int, *, multiplier: int = 12) -> int:
        if delta == 0:
            return 0
        base_units = max(1, abs(int(delta)) // 120)
        return base_units * multiplier

    def _scroll_mandatory_horizontally(direction: int, units: int) -> str:
        mand_tree.xview_scroll(direction * units, "units")
        return "break"

    def _on_mandatory_shift_mousewheel(event: tk.Event) -> str:
        delta = int(getattr(event, "delta", 0))
        units = _mandatory_scroll_units(delta)
        if units <= 0:
            return "break"
        direction = -1 if delta > 0 else 1
        return _scroll_mandatory_horizontally(direction, units)

    def _on_mandatory_shift_button4(_event: tk.Event) -> str:
        return _scroll_mandatory_horizontally(-1, 3)

    def _on_mandatory_shift_button5(_event: tk.Event) -> str:
        return _scroll_mandatory_horizontally(1, 3)

    for widget in (mand_tree, mand_xscroll):
        if widget is not None:
            widget.bind("<Shift-MouseWheel>", _on_mandatory_shift_mousewheel, add="+")
            widget.bind("<Shift-Button-4>", _on_mandatory_shift_button4, add="+")
            widget.bind("<Shift-Button-5>", _on_mandatory_shift_button5, add="+")


def mandatory_date_text(expense: Any) -> str:
    return (
        expense.date.isoformat()
        if getattr(expense.date, "isoformat", None) is not None
        else str(expense.date or "")
    )


def populate_mandatory_tree(
    mand_tree: ttk.Treeview,
    *,
    context: Any,
    base_currency_code: str,
) -> None:
    mand_tree.heading("kzt", text=context.controller.get_display_currency_code())
    for iid in mand_tree.get_children():
        mand_tree.delete(iid)
    expenses = context.controller.load_mandatory_expenses()
    for idx, expense in enumerate(expenses):
        values = (
            str(idx),
            f"{float(expense.amount_original or 0.0):,.2f}",
            str(expense.currency or base_currency_code).upper(),
            context.controller.format_display_amount(float(expense.amount_base or 0.0)),
            str(expense.category or ""),
            str(expense.description or ""),
            str(expense.period or ""),
            mandatory_date_text(expense),
            "✓" if bool(expense.auto_pay) else "",
        )
        mand_tree.insert("", "end", iid=str(idx), values=values)
