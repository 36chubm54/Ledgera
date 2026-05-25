"""Debts tab builder."""

# ruff: noqa: E501

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from gui.i18n import tr
from gui.ui_theme import PAD_LG, PAD_SM, PAD_XL, get_palette

from ..support.actions import (
    close_selected_debt,
    create_debt_action,
    delete_selected_debt,
    refresh_wallets,
    run_on_selected,
)
from ..support.forms import build_action_form, build_create_form
from ..support.history_section import (
    build_history_section,
    redraw_progress,
    refresh_debt_tree,
    refresh_history,
)
from ..support.keyboard import bind_control_shortcuts, bind_focus_navigation, bind_submit_navigation
from .contracts import DebtsTabBindings, DebtsTabContext, refresh_debts_views


def build_debts_tab(
    parent: tk.Frame | ttk.Frame,
    *,
    context: DebtsTabContext,
    messagebox_module,
) -> DebtsTabBindings:
    def format_display_amount(amount: float, precision: int = 2) -> str:
        return context.controller.format_display_amount(amount, precision=precision)

    def _base_currency_code() -> str:
        getter = getattr(context.controller, "get_base_currency_code", None)
        if callable(getter):
            return str(getter() or "").strip().upper() or "KZT"
        return "KZT"

    palette = get_palette()
    parent.grid_columnconfigure(0, weight=2, uniform="debts")
    parent.grid_columnconfigure(1, weight=5, uniform="debts")
    parent.grid_rowconfigure(0, weight=1)

    left = ttk.Frame(parent)
    left.grid(row=0, column=0, sticky="nsew", padx=(PAD_XL, PAD_SM), pady=PAD_LG)
    left.grid_columnconfigure(0, weight=1)
    right = ttk.Frame(parent)
    right.grid(row=0, column=1, sticky="nsew", padx=(PAD_SM, PAD_XL), pady=PAD_LG)
    right.grid_columnconfigure(0, weight=1)
    right.grid_rowconfigure(0, weight=1)
    right.grid_rowconfigure(1, weight=0)
    right.grid_rowconfigure(2, weight=0)
    right.grid_rowconfigure(3, weight=1)

    section = build_history_section(right, left, palette=palette)
    create_form = None
    action_form = None

    def _refresh_wallets() -> dict[str, int]:
        assert create_form is not None
        assert action_form is not None
        return refresh_wallets(
            context,
            wallet_menu=create_form.wallet_menu,
            action_wallet_menu=action_form.action_wallet_menu,
            wallet_var=create_form.wallet_var,
            action_wallet_var=action_form.action_wallet_var,
        )

    wallet_map: dict[str, int] = {}

    def _refresh() -> None:
        nonlocal wallet_map
        wallet_map = _refresh_wallets()
        refresh_debt_tree(context, section, format_display_amount=format_display_amount)

    def _create() -> None:
        assert create_form is not None
        create_debt_action(
            context=context,
            messagebox_module=messagebox_module,
            kind_label=create_form.kind_var.get(),
            debt_label=create_form.debt_label,
            contact_entry=create_form.contact_entry,
            amount_entry=create_form.amount_entry,
            date_entry=create_form.date_entry,
            description_entry=create_form.description_entry,
            wallet_var=create_form.wallet_var,
            wallet_map=wallet_map,
            refresh=_refresh,
            base_currency_code=_base_currency_code,
        )

    def _pay() -> None:
        assert action_form is not None
        success = run_on_selected(
            context=context,
            messagebox_module=messagebox_module,
            title=tr("debts.error.payment_title", "Ошибка погашения"),
            debt_tree=section.debt_tree,
            action_amount_entry=action_form.action_amount_entry,
            action_date_entry=action_form.action_date_entry,
            action_wallet_var=action_form.action_wallet_var,
            wallet_map=wallet_map,
            refresh=_refresh,
            action=lambda debt, amount, date_text, wallet_id: (
                context.controller.register_debt_payment(
                    debt_id=debt.id,
                    wallet_id=int(wallet_id),  # type: ignore[arg-type]
                    amount_base=amount,
                    payment_date=date_text,
                )
            ),
        )
        if success:
            refresh_debts_views(context)

    def _write_off() -> None:
        assert action_form is not None
        run_on_selected(
            context=context,
            messagebox_module=messagebox_module,
            title=tr("debts.error.writeoff_title", "Ошибка списания"),
            debt_tree=section.debt_tree,
            action_amount_entry=action_form.action_amount_entry,
            action_date_entry=action_form.action_date_entry,
            action_wallet_var=action_form.action_wallet_var,
            wallet_map=wallet_map,
            refresh=_refresh,
            wallet_optional=True,
            action=lambda debt, amount, date_text, _wallet_id: (
                context.controller.register_debt_write_off(
                    debt_id=debt.id,
                    amount_base=amount,
                    payment_date=date_text,
                )
            ),
        )

    def _close() -> None:
        assert action_form is not None
        close_selected_debt(
            context=context,
            messagebox_module=messagebox_module,
            debt_tree=section.debt_tree,
            action_date_entry=action_form.action_date_entry,
            action_wallet_var=action_form.action_wallet_var,
            wallet_map=wallet_map,
            refresh=_refresh,
        )

    def _delete() -> None:
        delete_selected_debt(
            context=context,
            messagebox_module=messagebox_module,
            debt_tree=section.debt_tree,
            refresh=_refresh,
        )

    create_form = build_create_form(left, on_save=_create)
    action_form = build_action_form(
        left,
        on_pay=_pay,
        on_write_off=_write_off,
        on_close=_close,
        on_delete=_delete,
        on_refresh=_refresh,
    )
    bind_submit_navigation(create_form.navigation_widgets, _create)
    bind_focus_navigation(action_form.navigation_widgets)
    for widget in action_form.navigation_widgets:
        bind_control_shortcuts(widget, {"p": _pay, "w": _write_off})

    section.progress_canvas.bind(
        "<Configure>",
        lambda _event: redraw_progress(section, format_display_amount=format_display_amount),
    )
    section.debt_tree.bind(
        "<<TreeviewSelect>>",
        lambda _event: refresh_history(
            context,
            section,
            format_display_amount=format_display_amount,
        ),
        add="+",
    )

    _refresh()
    return DebtsTabBindings(
        debt_tree=section.debt_tree,
        history_tree=section.history_tree,
        refresh=_refresh,
        add_debt=_create,
        pay_debt=_pay,
        write_off_debt=_write_off,
        delete_debt=_delete,
    )
