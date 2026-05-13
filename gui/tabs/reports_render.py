from __future__ import annotations

import tkinter as tk
from typing import Any

from gui.i18n import tr
from gui.record_colors import foreground_for_kind
from services.report_service import build_category_group_rows

from .reports_layout import ReportsUiHandles


def refresh_wallets(owner: Any, ui: ReportsUiHandles) -> None:
    selected = owner.wallet_var.get()
    all_wallets = tr("reports.wallets.all", "Все кошельки")
    owner._wallet_label_to_id = {all_wallets: None}
    for wallet in owner._controller.load_active_wallets():
        owner._wallet_label_to_id[f"[{wallet.id}] {wallet.name} ({wallet.currency})"] = wallet.id
    labels = list(owner._wallet_label_to_id.keys())
    selected_label = selected if selected in owner._wallet_label_to_id else all_wallets
    ui.wallet_menu["values"] = labels
    owner.wallet_var.set(selected_label)


def refresh_summary_only(owner: Any, ui: ReportsUiHandles) -> None:
    result = owner._last_result
    if result is None:
        return
    currency_code = owner._context.controller.get_display_currency_code()
    fmt_money = owner._context.controller.format_display_money
    summary = result.summary
    wallet_specific = result.filters.wallet_id is not None
    ui.summary_labels["net_worth_fixed"].config(
        text=(
            tr("reports.summary.wallet_balance_fixed", "Баланс кошелька (исторический):")
            if wallet_specific
            else tr("reports.summary.net_worth_fixed", "Чистый капитал (исторический):")
        )
    )
    ui.summary_labels["net_worth_current"].config(
        text=(
            tr("reports.summary.wallet_balance_current", "Баланс кошелька (текущий):")
            if wallet_specific
            else tr("reports.summary.net_worth_current", "Чистый капитал (текущий):")
        )
    )
    ui.operations_tree.heading("amount", text=currency_code)
    ui.monthly_tree.heading(
        "income",
        text=tr("reports.income", "Доход") + f" ({currency_code})",
    )
    ui.monthly_tree.heading("expense", text=tr("reports.expense", "Расход") + f" ({currency_code})")
    ui.summary_values["net_worth_fixed"].config(text=fmt_money(summary.net_worth_fixed))
    ui.summary_values["net_worth_current"].config(text=fmt_money(summary.net_worth_current))
    ui.summary_values["initial_balance"].config(text=fmt_money(summary.initial_balance))
    ui.summary_values["records_total"].config(text=fmt_money(summary.records_total_fixed))
    final_value = (
        summary.final_balance_current
        if owner.totals_mode_var.get() == "current"
        else summary.final_balance_fixed
    )
    ui.summary_values["final_balance"].config(text=fmt_money(final_value))
    ui.summary_values["fx_difference"].config(text=fmt_money(summary.fx_difference))
    if summary.active_tag:
        owner._group_status_var.set(
            tr("reports.filter.tag", "Фильтр по тегу: {tag}", tag=summary.active_tag)
        )
    elif not owner._group_drill_category:
        owner._group_status_var.set("")


def refresh_operations_table(owner: Any, ui: ReportsUiHandles) -> None:
    for iid in ui.operations_tree.get_children():
        ui.operations_tree.delete(iid)
    result = owner._last_result
    if result is None:
        return

    if not owner.group_var.get():
        for row in result.operations:
            tags = (row.kind,) if foreground_for_kind(row.kind) else ()
            ui.operations_tree.insert(
                "",
                "end",
                values=(
                    row.date,
                    owner._display_type_label(row.type_label),
                    owner._display_category_label(row.category),
                    row.tags_text,
                    owner._context.controller.format_display_amount(row.amount_base),
                ),
                tags=tags,
            )
        return

    owner._group_iid_to_category = {}
    drill_category = (owner._group_drill_category or "").strip()
    if drill_category:
        for row in result.operations:
            if row.category != drill_category:
                continue
            tags = (row.kind,) if foreground_for_kind(row.kind) else ()
            ui.operations_tree.insert(
                "",
                "end",
                values=(
                    row.date,
                    owner._display_type_label(row.type_label),
                    owner._display_category_label(row.category),
                    row.tags_text,
                    owner._context.controller.format_display_amount(row.amount_base),
                ),
                tags=tags,
            )
        return

    for index, row in enumerate(build_category_group_rows(result.operations), start=1):
        category = owner._display_category_label(row.category)
        iid = f"cat_{index}"
        owner._group_iid_to_category[iid] = (
            "" if str(row.category or "").strip() == "<Empty>" else str(row.category)
        )
        ui.operations_tree.insert(
            "",
            "end",
            iid=iid,
            values=(
                "",
                tr("reports.group.ops", "Опер.: {count}", count=row.operations_count),
                category,
                "",
                owner._context.controller.format_display_amount(row.total_base),
            ),
        )


def refresh_monthly_table(owner: Any, ui: ReportsUiHandles) -> None:
    for iid in ui.monthly_tree.get_children():
        ui.monthly_tree.delete(iid)
    result = owner._last_result
    if result is None:
        return
    for row in result.monthly:
        ui.monthly_tree.insert(
            "",
            "end",
            values=(
                row.month,
                owner._context.controller.format_display_amount(row.income),
                owner._context.controller.format_display_amount(row.expense),
            ),
        )


def refresh_category_sources(owner: Any, ui: ReportsUiHandles) -> None:
    result = owner._last_result
    if result is None:
        return
    ui.category_combo["values"] = [""] + result.categories
    tag_values = [tag.name for tag in owner._context.controller.list_tags()]
    ui.tag_combo["values"] = [""] + tag_values


def apply_group_ui_state(owner: Any, ui: ReportsUiHandles) -> None:
    enabled = bool(owner.group_var.get())
    try:
        ui.group_back_button.configure(state=("normal" if enabled else "disabled"))
    except tk.TclError:
        pass
    if not enabled:
        owner._group_drill_category = None
        owner._group_status_var.set("")
    else:
        owner._group_status_var.set(
            tr(
                "reports.group.category",
                "Категория: {category}",
                category=owner._group_drill_category,
            )
            if owner._group_drill_category
            else tr("reports.grouped_hint", "Сгруппированный вид (двойной щелчок по категории) ⓘ")
        )
    refresh_operations_table(owner, ui)
