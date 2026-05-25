from __future__ import annotations

# ruff: noqa: E501
from tkinter import ttk

from gui.i18n import tr

from .prompts import DistributionActionUi
from .results_section import selected_result_month
from .structure_section import selected_item_id


def ask_pct(
    title: str,
    prompt: str,
    *,
    parent,
    ui: DistributionActionUi,
    initialvalue: str = "0.00",
) -> float | None:
    raw_value = ui.ask_numeric_text_fn(
        title,
        prompt,
        parent=parent,
        initialvalue=initialvalue,
        validator=lambda _value: None,
    )
    if raw_value is None:
        return None
    return float(raw_value)


def add_item(*, context, parent, refresh_all, ui: DistributionActionUi) -> None:
    name = ui.ask_text_fn(
        tr("distribution.dialog.new_item", "Новый элемент"),
        tr("distribution.dialog.item_name", "Название элемента:"),
        parent=parent,
    )
    if not name:
        return
    group_name = ui.ask_text_fn(
        tr("common.group", "Группа"),
        tr("distribution.dialog.group_name", "Необязательное имя группы:"),
        parent=parent,
    )
    pct = ask_pct(
        tr("distribution.dialog.percent", "Процент"),
        tr("distribution.dialog.percent_total", "Процент от общего месячного денежного потока:"),
        parent=parent,
        ui=ui,
    )
    if pct is None:
        return
    try:
        context.controller.create_distribution_item(name, group_name=group_name or "", pct=pct)
    except ValueError as exc:
        ui.messagebox_module.showerror(tr("tab.distribution", "Распределение"), str(exc))
        return
    refresh_all()


def add_subitem(
    *, context, parent, structure_tree: ttk.Treeview, refresh_all, ui: DistributionActionUi
) -> None:
    item_id = selected_item_id(structure_tree)
    if item_id is None:
        ui.messagebox_module.showerror(
            tr("common.error", "Ошибка"),
            tr("distribution.error.select_top_level", "Сначала выберите элемент верхнего уровня."),
        )
        return
    name = ui.ask_text_fn(
        tr("distribution.dialog.new_subitem", "Новый подэлемент"),
        tr("distribution.dialog.subitem_name", "Название подэлемента:"),
        parent=parent,
    )
    if not name:
        return
    pct = ask_pct(
        tr("distribution.dialog.percent", "Процент"),
        tr("distribution.dialog.percent_parent", "Процент от родительского элемента:"),
        parent=parent,
        ui=ui,
    )
    if pct is None:
        return
    try:
        context.controller.create_distribution_subitem(item_id, name, pct=pct)
    except ValueError as exc:
        ui.messagebox_module.showerror(tr("tab.distribution", "Распределение"), str(exc))
        return
    refresh_all()


def edit_percent(
    *, context, parent, structure_tree: ttk.Treeview, refresh_all, ui: DistributionActionUi
) -> None:
    selection = structure_tree.selection()
    if not selection:
        ui.messagebox_module.showerror(
            tr("common.error", "Ошибка"),
            tr("distribution.error.select_item", "Сначала выберите элемент или подэлемент."),
        )
        return
    iid = selection[0]
    if not (iid.startswith("item_") or iid.startswith("sub_")):
        ui.messagebox_module.showerror(
            tr("common.error", "Ошибка"),
            tr(
                "distribution.error.select_not_group",
                "Выберите элемент или подэлемент, а не заголовок группы.",
            ),
        )
        return
    current_value = str(structure_tree.item(iid, "values")[0]).rstrip("%").strip() or "0.00"
    pct = ask_pct(
        tr("distribution.dialog.edit_percent", "Изменить процент"),
        tr("distribution.dialog.new_percent", "Новый процент:"),
        parent=parent,
        ui=ui,
        initialvalue=current_value,
    )
    if pct is None:
        return
    try:
        if iid.startswith("item_"):
            context.controller.update_distribution_item_pct(int(iid.split("_", 1)[1]), pct)
        else:
            context.controller.update_distribution_subitem_pct(int(iid.split("_", 1)[1]), pct)
    except ValueError as exc:
        ui.messagebox_module.showerror(
            tr("distribution.error.title", "Ошибка распределения"), str(exc)
        )
        return
    refresh_all()


def rename_selected(
    *, context, parent, structure_tree: ttk.Treeview, refresh_all, ui: DistributionActionUi
) -> None:
    selection = structure_tree.selection()
    if not selection:
        ui.messagebox_module.showerror(
            tr("distribution.error.selection_title", "Требуется выбор"),
            tr(
                "distribution.error.selection_item_or_subitem",
                "Сначала выберите элемент или подэлемент.",
            ),
        )
        return
    iid = selection[0]
    if not (iid.startswith("item_") or iid.startswith("sub_")):
        ui.messagebox_module.showerror(
            tr("distribution.error.selection_title", "Требуется выбор"),
            tr(
                "distribution.error.selection_not_group_header",
                "Выберите элемент или подэлемент, а не заголовок группы.",
            ),
        )
        return
    current_name = structure_tree.item(iid, "text").strip()
    new_name = ui.ask_text_fn(
        tr("distribution.dialog.rename", "Переименование"),
        tr("distribution.dialog.new_name", "Новое имя:"),
        parent=parent,
        initialvalue=current_name,
    )
    if not new_name:
        return
    try:
        if iid.startswith("item_"):
            context.controller.update_distribution_item_name(int(iid.split("_", 1)[1]), new_name)
        else:
            context.controller.update_distribution_subitem_name(int(iid.split("_", 1)[1]), new_name)
    except ValueError as exc:
        ui.messagebox_module.showerror(
            tr("distribution.error.title", "Ошибка распределения"), str(exc)
        )
        return
    refresh_all()


def delete_selected(
    *, context, parent, structure_tree: ttk.Treeview, refresh_all, ui: DistributionActionUi
) -> None:
    selection = structure_tree.selection()
    if not selection:
        ui.messagebox_module.showerror(
            tr("distribution.error.selection_title", "Требуется выбор"),
            tr(
                "distribution.error.selection_delete_item",
                "Выберите элемент или подэлемент для удаления.",
            ),
        )
        return
    iid = selection[0]
    if not (iid.startswith("item_") or iid.startswith("sub_")):
        ui.messagebox_module.showerror(
            tr("distribution.error.selection_title", "Требуется выбор"),
            tr(
                "distribution.error.delete_group_header_forbidden",
                "Заголовки групп нельзя удалять напрямую.",
            ),
        )
        return
    name = structure_tree.item(iid, "text").strip()
    message = tr("distribution.confirm.delete_item", "Удалить '{name}'?", name=name)
    if iid.startswith("item_"):
        message += "\n" + tr(
            "distribution.confirm.delete_item_with_children",
            "Все дочерние подэлементы также будут удалены.",
        )
    if not ui.messagebox_module.askyesno(
        tr("distribution.confirm.delete_title", "Подтвердите удаление"),
        message,
        parent=parent,
    ):
        return
    try:
        if iid.startswith("item_"):
            context.controller.delete_distribution_item(int(iid.split("_", 1)[1]))
        else:
            context.controller.delete_distribution_subitem(int(iid.split("_", 1)[1]))
    except ValueError as exc:
        ui.messagebox_module.showerror(
            tr("distribution.error.title", "Ошибка распределения"), str(exc)
        )
        return
    refresh_all()


def toggle_fixed_row(
    *,
    context,
    parent,
    results_tree: ttk.Treeview,
    refresh_results,
    update_fix_button_state,
    ui: DistributionActionUi,
) -> None:
    month = selected_result_month(results_tree)
    if month is None:
        ui.messagebox_module.showerror(
            tr("common.error", "Ошибка"),
            tr("distribution.error.select_month", "Сначала выберите месяц в таблице."),
        )
        return
    try:
        context.controller.toggle_distribution_month_fixed(month)
    except ValueError as exc:
        ui.messagebox_module.showinfo(
            tr("tab.distribution", "Распределение"), str(exc), parent=parent
        )
        update_fix_button_state()
        return
    refresh_results()
    if results_tree.exists(month):
        results_tree.selection_set(month)
        results_tree.focus(month)
    update_fix_button_state()
