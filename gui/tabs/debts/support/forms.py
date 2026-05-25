from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from datetime import date
from tkinter import ttk

from gui.combobox_compat import enable_wayland_combobox_support
from gui.i18n import tr
from gui.ui_theme import PAD_LG, PAD_SM, PAD_XS, create_card_section


@dataclass(slots=True)
class DebtsCreateForm:
    kind_var: tk.StringVar
    debt_label: str
    kind_combo: ttk.Combobox
    contact_entry: ttk.Entry
    amount_entry: ttk.Entry
    date_entry: ttk.Entry
    wallet_var: tk.StringVar
    wallet_menu: ttk.Combobox
    description_entry: ttk.Entry
    save_button: ttk.Button
    navigation_widgets: list[tk.Misc]


@dataclass(slots=True)
class DebtsActionForm:
    action_amount_entry: ttk.Entry
    action_date_entry: ttk.Entry
    action_wallet_var: tk.StringVar
    action_wallet_menu: ttk.Combobox
    pay_button: ttk.Button
    write_off_button: ttk.Button
    close_button: ttk.Button
    delete_button: ttk.Button
    refresh_button: ttk.Button
    navigation_widgets: list[tk.Misc]


def build_create_form(left, *, on_save) -> DebtsCreateForm:
    create_card = create_card_section(left, tr("debts.create.title", "Новый долг / заем"))
    create_card.grid(row=0, column=0, sticky="ew")
    create_frame = create_card.winfo_children()[-1]
    create_frame.grid_columnconfigure(1, weight=1)

    ttk.Label(create_frame, text=tr("common.type", "Тип:"), style="FormField.TLabel").grid(
        row=0, column=0, sticky="w", padx=PAD_SM, pady=PAD_XS
    )
    debt_label = tr("debts.kind.debt", "Долг")
    loan_label = tr("debts.kind.loan", "Заем")
    kind_var = tk.StringVar(value=debt_label)
    kind_combo = ttk.Combobox(
        create_frame,
        textvariable=kind_var,
        values=[debt_label, loan_label],
        state="readonly",
    )
    kind_combo.grid(row=0, column=1, sticky="ew", padx=PAD_SM, pady=PAD_XS)
    enable_wayland_combobox_support(kind_combo, bind_down=False)

    ttk.Label(create_frame, text=tr("debts.contact", "Контакт:"), style="FormField.TLabel").grid(
        row=1, column=0, sticky="w", padx=PAD_SM, pady=PAD_XS
    )
    contact_entry = ttk.Entry(create_frame)
    contact_entry.grid(row=1, column=1, sticky="ew", padx=PAD_SM, pady=PAD_XS)

    ttk.Label(
        create_frame,
        text=tr("debts.amount", "Сумма (валюта базы):"),
        style="FormField.TLabel",
    ).grid(row=2, column=0, sticky="w", padx=PAD_SM, pady=PAD_XS)
    amount_entry = ttk.Entry(create_frame)
    amount_entry.grid(row=2, column=1, sticky="ew", padx=PAD_SM, pady=PAD_XS)

    ttk.Label(create_frame, text=tr("common.date", "Дата:"), style="FormField.TLabel").grid(
        row=3, column=0, sticky="w", padx=PAD_SM, pady=PAD_XS
    )
    date_entry = ttk.Entry(create_frame)
    date_entry.grid(row=3, column=1, sticky="ew", padx=PAD_SM, pady=PAD_XS)
    date_entry.insert(0, date.today().isoformat())

    ttk.Label(create_frame, text=tr("common.wallet", "Кошелек:"), style="FormField.TLabel").grid(
        row=4, column=0, sticky="w", padx=PAD_SM, pady=PAD_XS
    )
    wallet_var = tk.StringVar(value="")
    wallet_menu = ttk.Combobox(create_frame, textvariable=wallet_var, values=[], state="readonly")
    wallet_menu.grid(row=4, column=1, sticky="ew", padx=PAD_SM, pady=PAD_XS)
    enable_wayland_combobox_support(wallet_menu, bind_down=False)

    ttk.Label(
        create_frame, text=tr("common.description", "Описание:"), style="FormField.TLabel"
    ).grid(row=5, column=0, sticky="w", padx=PAD_SM, pady=PAD_XS)
    description_entry = ttk.Entry(create_frame)
    description_entry.grid(row=5, column=1, sticky="ew", padx=PAD_SM, pady=PAD_XS)

    save_button = ttk.Button(
        create_frame,
        text=tr("debts.save", "Сохранить"),
        style="Primary.TButton",
        command=on_save,
    )
    save_button.grid(row=6, column=0, columnspan=2, sticky="ew", padx=6, pady=8)

    navigation_widgets: list[tk.Misc] = [
        kind_combo,
        contact_entry,
        amount_entry,
        date_entry,
        wallet_menu,
        description_entry,
        save_button,
    ]
    return DebtsCreateForm(
        kind_var=kind_var,
        debt_label=debt_label,
        kind_combo=kind_combo,
        contact_entry=contact_entry,
        amount_entry=amount_entry,
        date_entry=date_entry,
        wallet_var=wallet_var,
        wallet_menu=wallet_menu,
        description_entry=description_entry,
        save_button=save_button,
        navigation_widgets=navigation_widgets,
    )


def build_action_form(
    left,
    *,
    on_pay,
    on_write_off,
    on_close,
    on_delete,
    on_refresh,
) -> DebtsActionForm:
    actions_card = create_card_section(
        left,
        tr("debts.actions.title", "Действия по выбранному долгу"),
    )
    actions_card.grid(row=1, column=0, sticky="ew", pady=(PAD_LG, 0))
    actions_frame = actions_card.winfo_children()[-1]
    actions_frame.grid_columnconfigure(1, weight=1)

    ttk.Label(
        actions_frame,
        text=tr("debts.amount", "Сумма (валюта базы):"),
        style="FormField.TLabel",
    ).grid(row=0, column=0, sticky="w", padx=PAD_SM, pady=PAD_XS)
    action_amount_entry = ttk.Entry(actions_frame)
    action_amount_entry.grid(row=0, column=1, sticky="ew", padx=PAD_SM, pady=PAD_XS)

    ttk.Label(actions_frame, text=tr("common.date", "Дата:"), style="FormField.TLabel").grid(
        row=1, column=0, sticky="w", padx=PAD_SM, pady=PAD_XS
    )
    action_date_entry = ttk.Entry(actions_frame)
    action_date_entry.grid(row=1, column=1, sticky="ew", padx=PAD_SM, pady=PAD_XS)
    action_date_entry.insert(0, date.today().isoformat())

    ttk.Label(actions_frame, text=tr("common.wallet", "Кошелек:"), style="FormField.TLabel").grid(
        row=2, column=0, sticky="w", padx=PAD_SM, pady=PAD_XS
    )
    action_wallet_var = tk.StringVar(value="")
    action_wallet_menu = ttk.Combobox(
        actions_frame,
        textvariable=action_wallet_var,
        values=[],
        state="readonly",
    )
    action_wallet_menu.grid(row=2, column=1, sticky="ew", padx=PAD_SM, pady=PAD_XS)
    enable_wayland_combobox_support(action_wallet_menu, bind_down=False)

    pay_button = ttk.Button(actions_frame, text=tr("debts.pay", "Погасить"), command=on_pay)
    pay_button.grid(row=3, column=0, sticky="ew", padx=6, pady=6)
    write_off_button = ttk.Button(
        actions_frame, text=tr("debts.write_off", "Списать"), command=on_write_off
    )
    write_off_button.grid(row=3, column=1, sticky="ew", padx=6, pady=6)
    close_button = ttk.Button(actions_frame, text=tr("debts.close", "Закрыть"), command=on_close)
    close_button.grid(row=4, column=0, sticky="ew", padx=6, pady=(0, 6))
    delete_button = ttk.Button(actions_frame, text=tr("debts.delete", "Удалить"), command=on_delete)
    delete_button.grid(row=4, column=1, sticky="ew", padx=6, pady=(0, 6))
    refresh_button = ttk.Button(
        actions_frame,
        text=tr("common.refresh", "Обновить"),
        command=on_refresh,
    )
    refresh_button.grid(row=5, column=0, columnspan=2, sticky="ew", padx=6, pady=(0, 6))

    navigation_widgets: list[tk.Misc] = [
        action_amount_entry,
        action_date_entry,
        action_wallet_menu,
        pay_button,
        write_off_button,
        close_button,
        delete_button,
        refresh_button,
    ]
    return DebtsActionForm(
        action_amount_entry=action_amount_entry,
        action_date_entry=action_date_entry,
        action_wallet_var=action_wallet_var,
        action_wallet_menu=action_wallet_menu,
        pay_button=pay_button,
        write_off_button=write_off_button,
        close_button=close_button,
        delete_button=delete_button,
        refresh_button=refresh_button,
        navigation_widgets=navigation_widgets,
    )
