from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from tkinter import ttk
from typing import Any, Protocol, cast

from gui.combobox_compat import enable_wayland_combobox_support
from gui.i18n import tr
from gui.ui_theme import PAD_SM, PAD_XS

FORM_LABEL_WIDTH = 20


class MandatoryWalletLike(Protocol):
    id: int
    name: str
    currency: str


class MandatoryWalletsController(Protocol):
    def load_active_wallets(self) -> list[MandatoryWalletLike]: ...


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


def _wallet_map(controller: MandatoryWalletsController) -> dict[str, int]:
    return {
        f"[{wallet.id}] {wallet.name} ({wallet.currency})": wallet.id
        for wallet in controller.load_active_wallets()
    }


def refresh_add_form_wallets(
    form: MandatoryAddFormFields,
    controller: MandatoryWalletsController,
) -> None:
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
    controller: MandatoryWalletsController,
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
    wallet_menu = ttk.Combobox(panel, textvariable=wallet_var, values=[], state="readonly")
    if stacked:
        wallet_menu.grid(row=row_index + 1, column=0, sticky="ew", padx=PAD_SM, pady=(0, PAD_XS))
    else:
        wallet_menu.grid(row=row_index, column=1, sticky="ew", padx=PAD_SM, pady=PAD_XS)
    enable_wayland_combobox_support(wallet_menu, bind_down=False)
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
    ).grid(row=row_index, column=0, sticky="w", padx=PAD_SM, pady=PAD_XS)
    widget.grid(row=row_index, column=1, sticky="ew", padx=PAD_SM, pady=PAD_XS)


def build_add_mandatory_panel(
    parent: tk.Misc,
    *,
    controller: MandatoryWalletsController,
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
        currency_entry.grid(row=1, column=1, columnspan=3, sticky="ew", padx=PAD_SM, pady=PAD_XS)

        form_label(2, tr("common.wallet", "Кошелек:"))
        wallet_var = tk.StringVar(value="")
        wallet_menu = ttk.Combobox(panel, textvariable=wallet_var, values=[], state="readonly")
        wallet_map = _wallet_map(controller)
        wallet_labels = list(wallet_map.keys()) or [""]
        wallet_menu["values"] = wallet_labels
        wallet_var.set(wallet_labels[0])
        wallet_menu.grid(row=2, column=1, columnspan=3, sticky="ew", padx=PAD_SM, pady=PAD_XS)
        enable_wayland_combobox_support(wallet_menu, bind_down=False)

        form_label(3, tr("mandatory.field.category", "Категория"))
        category_entry = ttk.Entry(panel)
        category_entry.insert(0, "Mandatory")
        category_entry.grid(row=3, column=1, columnspan=3, sticky="ew", padx=PAD_SM, pady=PAD_XS)

        form_label(4, tr("common.description", "Описание:"))
        description_entry = ttk.Entry(panel)
        description_entry.grid(row=4, column=1, columnspan=3, sticky="ew", padx=PAD_SM, pady=PAD_XS)

        form_label(5, tr("common.period", "Период:"))
        period_var = tk.StringVar(value="monthly")
        period_combo = ttk.Combobox(
            panel,
            textvariable=period_var,
            values=["daily", "weekly", "monthly", "yearly"],
            state="readonly",
        )
        period_combo.grid(row=5, column=1, columnspan=3, sticky="ew", padx=PAD_SM, pady=PAD_XS)
        enable_wayland_combobox_support(period_combo, bind_down=False)

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
    enable_wayland_combobox_support(period_combo, bind_down=False)
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
    controller: MandatoryWalletsController,
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
    enable_wayland_combobox_support(period_combo, bind_down=False)
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
    controller: MandatoryWalletsController,
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


def mandatory_date_text(expense: Any) -> str:
    return (
        expense.date.isoformat()
        if getattr(expense.date, "isoformat", None) is not None
        else str(expense.date or "")
    )
