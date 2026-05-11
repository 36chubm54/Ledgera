"""Operations tab — CRUD operations for financial records and transfers, import and export"""

from __future__ import annotations

import logging
import os
import tkinter as tk
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date
from tkinter import filedialog, ttk
from typing import Any, Protocol, cast

from domain.errors import DomainError
from domain.import_policy import ImportPolicy
from domain.import_result import ImportResult
from gui.helpers import open_in_file_manager
from gui.i18n import tr
from gui.logging_utils import log_ui_error
from gui.tabs.operations_support import (
    refresh_operation_views,
    safe_destroy,
    show_import_preview_dialog,
)
from gui.tooltip import Tooltip, show_popup_tooltip
from gui.ui_helpers import (
    ask_confirm,
    enable_treeview_column_autosize,
    show_error,
    show_info,
    show_warning,
)
from gui.ui_theme import (
    FONT_FAMILY,
    PAD_LG,
    PAD_SM,
    PAD_XL,
    PAD_XS,
    create_card_section,
    enable_treeview_zebra,
    get_palette,
)
from utils.tag_utils import (
    MAX_TAGS_PER_RECORD,
    TAG_COLOR_PALETTE,
    find_numeric_only_tags,
    normalize_tag_name,
    parse_tag_string,
)

logger = logging.getLogger(__name__)


class OperationsTabContext(Protocol):
    controller: Any
    repository: Any
    _record_id_to_repo_index: dict[str, int]
    _record_id_to_domain_id: dict[str, int]

    def _refresh_list(self) -> None: ...

    def _refresh_charts(self) -> None: ...

    def _refresh_wallets(self) -> None: ...

    def _refresh_budgets(self) -> None: ...

    def _refresh_all(self) -> None: ...

    def _run_background(
        self,
        task: Callable[[], Any],
        *,
        on_success: Callable[[Any], None],
        on_error: Callable[[BaseException], None] | None = None,
        busy_message: str = tr("app.busy.default", "Выполняется операция..."),
    ) -> None: ...

    def _import_policy_from_ui(self, mode_label: str) -> ImportPolicy: ...


@dataclass(slots=True)
class OperationsTabBindings:
    records_tree: ttk.Treeview
    tags_tree: ttk.Treeview
    refresh_operation_wallet_menu: Callable[[], None]
    refresh_transfer_wallet_menus: Callable[[], None]
    set_type_income: Callable[[], None]
    set_type_expense: Callable[[], None]
    save_record: Callable[[], None]
    select_first: Callable[[], None]
    select_last: Callable[[], None]
    delete_selected: Callable[[], None]
    delete_all: Callable[[], None]
    edit_selected: Callable[[], None]
    inline_editor_active: Callable[[], bool]


def build_operations_tab(
    parent: tk.Frame | ttk.Frame,
    context: OperationsTabContext,
    import_formats: dict[str, dict[str, str]],
) -> OperationsTabBindings:
    parent.grid_columnconfigure(0, weight=2, uniform="operations")
    parent.grid_columnconfigure(1, weight=5, uniform="operations")
    parent.grid_rowconfigure(0, weight=1)

    left_frame = ttk.Frame(parent)
    left_frame.grid(row=0, column=0, sticky="nsew", padx=(PAD_XL, PAD_SM), pady=PAD_LG)
    left_frame.grid_columnconfigure(0, weight=1)
    left_frame.grid_rowconfigure(0, weight=1)

    paned = ttk.PanedWindow(left_frame, orient=tk.VERTICAL)
    paned.grid(row=0, column=0, sticky="nsew")

    form_card = create_card_section(paned, tr("operations.new", "Новая операция"))
    paned.add(form_card, weight=1)
    form_frame = form_card.winfo_children()[-1]
    form_frame.grid_columnconfigure(1, weight=1)
    form_frame.grid_columnconfigure(2, weight=1)
    form_frame.grid_columnconfigure(3, weight=0)

    label_width = 12

    def _form_label(row: int, text: str) -> ttk.Label:
        label = ttk.Label(form_frame, text=text, width=label_width, anchor="w")
        label.grid(row=row, column=0, sticky="w", padx=PAD_SM, pady=PAD_XS)
        return label

    palette = get_palette()

    def _base_currency_code() -> str:
        getter = getattr(context.controller, "get_base_currency_code", None)
        if callable(getter):
            return str(getter() or "").strip().upper() or "KZT"
        return "KZT"

    def _is_kzt_currency(value: object) -> bool:
        return str(value or _base_currency_code()).strip().upper() == _base_currency_code()

    def _amount_edit_label_text(currency: object) -> str:
        if _is_kzt_currency(currency):
            return tr("common.amount", "Сумма:")
        return tr("operations.edit.amount_equivalent", "Эквивалент в валюте базы:")

    amount_edit_tooltip_text = tr(
        "operations.edit.amount_tooltip",
        "Для операций в валюте базы это основная сумма операции."
        "\nДля других валют это эквивалент в валюте базы и он влияет на курс операции.",
    )

    income_label = tr("operations.type.income", "Доход")
    expense_label = tr("operations.type.expense", "Расход")
    _form_label(0, tr("common.type", "Тип:"))
    type_options = [income_label, expense_label]
    type_combo = ttk.Combobox(form_frame, values=type_options, state="readonly")
    type_combo.set(income_label)
    type_combo.grid(row=0, column=1, columnspan=3, sticky="ew", padx=PAD_SM, pady=PAD_XS)

    _form_label(1, tr("common.date", "Дата:"))
    date_entry = ttk.Entry(form_frame)
    date_entry.grid(row=1, column=1, columnspan=3, sticky="ew", padx=PAD_SM, pady=PAD_XS)
    date_entry.insert(0, date.today().isoformat())

    _form_label(2, tr("common.amount", "Сумма:"))
    amount_entry = ttk.Entry(form_frame)
    amount_entry.grid(row=2, column=1, columnspan=3, sticky="ew", padx=PAD_SM, pady=PAD_XS)

    _form_label(3, tr("common.currency", "Валюта:"))
    currency_entry = ttk.Entry(form_frame)
    currency_entry.insert(0, _base_currency_code())
    currency_entry.grid(row=3, column=1, columnspan=3, sticky="ew", padx=PAD_SM, pady=PAD_XS)

    _form_label(4, tr("common.category", "Категория:"))
    category_combo = ttk.Combobox(form_frame, state="normal")
    category_combo.insert(0, "General")
    category_combo.grid(row=4, column=1, columnspan=3, sticky="ew", padx=PAD_SM, pady=PAD_XS)

    _form_label(5, tr("common.description", "Описание:"))
    description_entry = ttk.Entry(form_frame)
    description_entry.grid(row=5, column=1, columnspan=3, sticky="ew", padx=PAD_SM, pady=PAD_XS)

    _form_label(6, tr("common.tags", "Теги:"))
    tags_combo = ttk.Combobox(form_frame, state="normal")
    tags_combo.grid(row=6, column=1, columnspan=2, sticky="ew", padx=PAD_SM, pady=PAD_XS)
    Tooltip(
        tags_combo,
        tr(
            "operations.tags.input_tooltip",
            "Введите до 3 тегов через запятую."
            "\nСписок подсказок предлагает существующие теги,"
            "\nновый тег можно дописать вручную."
            "\nТеги приводятся к нижнему регистру,"
            "\nпробелы и спецсимволы удаляются.",
        ),
    )
    selected_tag_color = {"value": TAG_COLOR_PALETTE[0]}
    tag_color_button = tk.Button(
        form_frame,
        width=3,
        height=1,
        relief="raised",
        bd=1,
        overrelief="sunken",
        bg=selected_tag_color["value"],
        activebackground=selected_tag_color["value"],
        highlightthickness=1,
        highlightbackground=palette.border_soft,
        cursor="hand2",
        takefocus=True,
    )
    tag_color_button.grid(
        row=6, column=3, sticky="e", padx=(0, PAD_SM), pady=PAD_XS, ipadx=4, ipady=4
    )
    Tooltip(
        tag_color_button,
        tr(
            "operations.tags.color_tooltip",
            "Цвет тега. Щелкните по квадрату, чтобы открыть палитру.",
        ),
    )

    tags_popup_state: dict[str, Any] = {"window": None, "listbox": None, "items": []}
    color_popup_state: dict[str, Any] = {"menu": None}
    tag_selection_state: dict[str, Any] = {"committed": (), "fragment": ""}

    _form_label(7, tr("common.wallet", "Кошелек:"))
    operation_wallet_var = tk.StringVar(value="")
    operation_wallet_menu = ttk.Combobox(
        form_frame,
        textvariable=operation_wallet_var,
        values=[],
        state="readonly",
    )
    operation_wallet_menu.grid(row=7, column=1, columnspan=3, sticky="ew", padx=PAD_SM, pady=PAD_XS)
    operation_wallet_map: dict[str, int] = {}

    def _set_tag_color(color: str) -> None:
        normalized = str(color or "").strip() or TAG_COLOR_PALETTE[0]
        selected_tag_color["value"] = normalized
        tag_color_button.configure(
            bg=normalized,
            activebackground=normalized,
            highlightbackground=palette.border_soft,
        )

    def _list_tags_safe() -> list[Any]:
        list_tags = getattr(context.controller, "list_tags", None)
        if not callable(list_tags):
            return []
        try:
            return list(cast(Iterable[Any], list_tags()))
        except (ValueError, RuntimeError, TypeError):
            return []

    def _sorted_tags_by_popularity() -> list[Any]:
        tags = _list_tags_safe()
        return sorted(
            tags,
            key=lambda tag: (
                -int(getattr(tag, "usage_count", 0)),
                str(getattr(tag, "name", "")).casefold(),
            ),
        )

    def _split_tag_input(raw_value: str) -> tuple[tuple[str, ...], str]:
        parts = str(raw_value or "").split(",")
        committed = parse_tag_string(",".join(parts[:-1])) if len(parts) > 1 else ()
        fragment = parts[-1].strip() if parts else ""
        return committed, fragment

    def _remember_tag_input_state(raw_value: str | None = None) -> tuple[tuple[str, ...], str]:
        committed, fragment = _split_tag_input(tags_combo.get() if raw_value is None else raw_value)
        tag_selection_state["committed"] = committed
        tag_selection_state["fragment"] = fragment
        return committed, fragment

    def _build_tag_suggestions(raw_value: str) -> list[Any]:
        committed, fragment = _split_tag_input(raw_value)
        committed_set = set(committed)
        normalized_fragment = normalize_tag_name(fragment)
        suggestions: list[Any] = []
        for tag in _sorted_tags_by_popularity():
            tag_name = str(getattr(tag, "name", "") or "")
            if not tag_name or tag_name in committed_set:
                continue
            if normalized_fragment and not tag_name.startswith(normalized_fragment):
                continue
            suggestions.append(tag)
        return suggestions

    def _next_free_color() -> str:
        used_colors = {str(getattr(tag, "color", "") or "") for tag in _list_tags_safe()}
        for color in TAG_COLOR_PALETTE:
            if color not in used_colors:
                return color
        return TAG_COLOR_PALETTE[0]

    def _sync_tag_color_from_input() -> None:
        committed, fragment = _split_tag_input(tags_combo.get())
        normalized_fragment = normalize_tag_name(fragment)
        tags_by_name = {str(getattr(tag, "name", "") or ""): tag for tag in _list_tags_safe()}
        if normalized_fragment and normalized_fragment in tags_by_name:
            _set_tag_color(
                str(getattr(tags_by_name[normalized_fragment], "color", "") or _next_free_color())
            )
            return
        if committed:
            last_tag = tags_by_name.get(committed[-1])
            if last_tag is not None:
                _set_tag_color(str(getattr(last_tag, "color", "") or _next_free_color()))
                return
        _set_tag_color(_next_free_color())

    def _hide_tags_popup(_event: object | None = None) -> None:
        window = tags_popup_state.get("window")
        if window is not None:
            try:
                window.destroy()
            except tk.TclError:
                pass
        tags_popup_state["window"] = None
        tags_popup_state["listbox"] = None
        tags_popup_state["items"] = []

    def _hide_color_popup(_event: object | None = None) -> None:
        menu = color_popup_state.get("menu")
        if menu is not None:
            try:
                menu.unpost()
            except tk.TclError:
                pass
            else:
                form_frame.after_idle(lambda current=menu: current.destroy())
        color_popup_state["menu"] = None
        form_frame.after(0, tags_combo.focus_set)

    def _select_tag_color(color: str) -> None:
        _set_tag_color(color)
        _hide_color_popup()

    def _apply_tag_selection(
        tag_name: str,
        *,
        committed_override: tuple[str, ...] | None = None,
    ) -> None:
        committed = (
            tuple(committed_override)
            if committed_override is not None
            else tuple(tag_selection_state.get("committed", ()) or ())
        )
        next_tags = [*committed, tag_name][:MAX_TAGS_PER_RECORD]
        text = ", ".join(next_tags)
        if len(next_tags) < MAX_TAGS_PER_RECORD:
            text = f"{text}, "
        tags_combo.delete(0, tk.END)
        tags_combo.insert(0, text)
        _remember_tag_input_state(text)
        _sync_tag_color_from_input()
        _hide_tags_popup()
        tags_combo.focus_set()
        tags_combo.icursor(tk.END)

    def _show_tags_popup() -> None:
        _remember_tag_input_state()
        suggestions = _build_tag_suggestions(tags_combo.get())
        tags_combo["values"] = [tag.name for tag in suggestions]
        if not suggestions:
            _hide_tags_popup()
            return
        _hide_tags_popup()
        popup = tk.Toplevel(form_frame)
        popup.wm_overrideredirect(True)
        popup.configure(bg=palette.border_soft)
        popup.transient(form_frame.winfo_toplevel())
        x = tags_combo.winfo_rootx()
        y = tags_combo.winfo_rooty() + tags_combo.winfo_height() + 2
        width = max(tags_combo.winfo_width(), 220)
        popup.wm_geometry(f"{width}x160+{x}+{y}")
        listbox = tk.Listbox(
            popup,
            activestyle="none",
            borderwidth=0,
            highlightthickness=0,
            font=(FONT_FAMILY, 10),
            selectmode=tk.SINGLE,
            bg=palette.surface_elevated,
            fg=palette.text_primary,
            selectbackground=palette.accent_blue,
            selectforeground=palette.surface_elevated,
        )
        listbox.pack(fill="both", expand=True, padx=1, pady=1)
        for index, tag in enumerate(suggestions):
            listbox.insert(tk.END, f"#{tag.name}")
            listbox.itemconfig(
                index,
                fg=str(getattr(tag, "color", "") or palette.text_primary),
                bg=palette.surface_elevated,
            )
        listbox.selection_set(0)
        listbox.activate(0)
        tags_popup_state["window"] = popup
        tags_popup_state["listbox"] = listbox
        tags_popup_state["items"] = suggestions

        def _confirm_selection(_event: tk.Event | None = None) -> str:
            selected = listbox.curselection()
            if not selected:
                return "break"
            chosen = suggestions[int(selected[0])]
            _apply_tag_selection(str(getattr(chosen, "name", "") or ""))
            return "break"

        listbox.bind("<Return>", _confirm_selection, add="+")
        listbox.bind("<Double-Button-1>", _confirm_selection, add="+")
        listbox.bind("<Escape>", lambda _event: (_hide_tags_popup(), "break")[1], add="+")
        popup.bind("<FocusOut>", _hide_tags_popup, add="+")

    def _show_color_popup() -> None:
        if color_popup_state.get("menu") is not None:
            _hide_color_popup()
            return
        _hide_color_popup()
        popup = tk.Menu(
            form_frame,
            tearoff=False,
            relief="solid",
            borderwidth=1,
            activeborderwidth=0,
            bg=palette.surface_elevated,
            fg=palette.text_primary,
        )
        for color in TAG_COLOR_PALETTE:
            popup.add_command(
                label=color,
                background=color,
                activebackground=color,
                command=lambda selected=color: _select_tag_color(selected),
            )
        x = tag_color_button.winfo_rootx()
        y = tag_color_button.winfo_rooty() + tag_color_button.winfo_height() + 2
        color_popup_state["menu"] = popup
        popup.post(x, y)

    def _prepare_native_tag_dropdown() -> None:
        _remember_tag_input_state()
        suggestions = _build_tag_suggestions(tags_combo.get())
        tags_combo["values"] = [tag.name for tag in suggestions]

    tags_combo.configure(postcommand=_prepare_native_tag_dropdown)

    def _refresh_category_combo() -> None:
        try:
            if type_combo.get() == income_label:
                category_combo["values"] = context.controller.get_income_categories()
            else:
                category_combo["values"] = context.controller.get_expense_categories()
        except (ValueError, RuntimeError):
            pass
        category_combo.set("General")

    def _on_type_change(*_args: object) -> None:
        _refresh_category_combo()

    def _set_type_income() -> None:
        type_combo.set(income_label)
        _on_type_change()

    def _set_type_expense() -> None:
        type_combo.set(expense_label)
        _on_type_change()

    def refresh_operation_wallet_menu() -> None:
        nonlocal operation_wallet_map
        wallets = context.controller.load_active_wallets()
        operation_wallet_map = {
            f"[{wallet.id}] {wallet.name} ({wallet.currency})": wallet.id for wallet in wallets
        }
        labels = list(operation_wallet_map.keys()) or [""]
        operation_wallet_menu["values"] = labels
        if operation_wallet_var.get() not in operation_wallet_map:
            operation_wallet_var.set(labels[0])

    refresh_operation_wallet_menu()
    _sync_tag_color_from_input()

    def _on_tags_key_release(event: tk.Event | None = None) -> None:
        if event is not None and event.keysym in {"Up", "Down", "Return", "Escape", "Tab"}:
            return
        _remember_tag_input_state()
        _sync_tag_color_from_input()
        _show_tags_popup()

    def _on_tags_down(_event: tk.Event | None = None) -> str:
        _show_tags_popup()
        listbox = tags_popup_state.get("listbox")
        if listbox is not None:
            listbox.focus_set()
        return "break"

    tags_combo.bind("<KeyRelease>", _on_tags_key_release, add="+")
    tags_combo.bind("<Down>", _on_tags_down, add="+")

    def _on_tags_combobox_selected(_event: tk.Event | None = None) -> str:
        chosen = normalize_tag_name(tags_combo.get())
        if not chosen:
            return "break"
        committed = tuple(tag_selection_state.get("committed", ()) or ())
        if chosen in committed:
            _apply_tag_selection(
                chosen, committed_override=tuple(tag for tag in committed if tag != chosen)
            )
        else:
            _apply_tag_selection(chosen, committed_override=committed)
        return "break"

    tags_combo.bind("<<ComboboxSelected>>", _on_tags_combobox_selected, add="+")
    tags_combo.bind("<Button-1>", lambda _event: tags_combo.after(0, _show_tags_popup), add="+")
    tags_combo.bind("<FocusOut>", lambda _event: tags_combo.after(100, _hide_tags_popup), add="+")
    tag_color_button.configure(command=_show_color_popup)
    tag_color_button.bind("<Return>", lambda _event: (_show_color_popup(), "break")[1], add="+")
    tag_color_button.bind("<space>", lambda _event: (_show_color_popup(), "break")[1], add="+")

    list_card = create_card_section(parent, tr("operations.journal", "Журнал операций"))
    list_card.grid(row=0, column=1, sticky="nsew", padx=(PAD_SM, PAD_XL), pady=PAD_LG)
    list_frame = list_card.winfo_children()[-1]
    list_frame.grid_rowconfigure(0, weight=1)
    list_frame.grid_columnconfigure(0, weight=1)

    tables_frame = ttk.Frame(list_frame)
    tables_frame.grid(row=0, column=0, sticky="nsew", padx=PAD_SM, pady=PAD_SM)
    tables_frame.grid_rowconfigure(0, weight=1)
    tables_frame.grid_columnconfigure(0, weight=4)
    tables_frame.grid_columnconfigure(1, weight=1)

    records_tree = ttk.Treeview(
        tables_frame,
        show="headings",
        selectmode="browse",
        columns=(
            "index",
            "date",
            "type",
            "category",
            "amount",
            "currency",
            "kzt",
            "wallets",
        ),
    )
    enable_treeview_zebra(records_tree)
    for col, text, width, minwidth, stretch, anchor in (
        ("index", "#", 50, 50, False, "e"),
        ("date", tr("common.date", "Дата"), 100, 100, False, "w"),
        ("type", tr("common.type_short", "Тип"), 110, 110, False, "w"),
        ("category", tr("common.category_short", "Категория"), 180, 180, True, "w"),
        ("amount", tr("common.amount", "Сумма"), 90, 90, False, "e"),
        ("currency", tr("operations.currency_short", "Вал."), 60, 60, False, "center"),
        ("kzt", "KZT", 100, 90, False, "e"),
        ("wallets", tr("operations.wallets", "Кошельки"), 120, 110, False, "center"),
    ):
        records_tree.heading(col, text=text)
        records_tree.column(col, width=width, minwidth=minwidth, stretch=stretch, anchor=anchor)  # type: ignore[arg-type]
    enable_treeview_column_autosize(records_tree, columns=("category",), max_width=360)
    records_tree.grid(row=0, column=0, sticky="nsew")

    tags_tree = ttk.Treeview(
        tables_frame,
        show="headings",
        selectmode="browse",
        columns=("tags",),
    )
    enable_treeview_zebra(tags_tree)
    tags_tree.heading("tags", text=tr("common.tags", "Теги"))
    tags_tree.column("tags", width=180, minwidth=140, stretch=True, anchor="w")
    enable_treeview_column_autosize(tags_tree, columns=("tags",), max_width=420)
    tags_tree.grid(row=0, column=1, sticky="nsew", padx=(PAD_SM, 0))
    tags_tooltip_window: tk.Toplevel | None = None
    tags_tooltip_text = {"value": ""}

    def _hide_tags_tooltip(_event: object | None = None) -> None:
        nonlocal tags_tooltip_window
        if tags_tooltip_window is not None:
            tags_tooltip_window.destroy()
            tags_tooltip_window = None
        tags_tooltip_text["value"] = ""

    def _show_tags_tooltip(event: tk.Event) -> None:
        nonlocal tags_tooltip_window
        row_id = tags_tree.identify_row(event.y)
        if not row_id:
            _hide_tags_tooltip()
            return
        values = tags_tree.item(row_id, "values")
        text = str(values[0] if values else "").strip()
        if not text:
            _hide_tags_tooltip()
            return
        if text == tags_tooltip_text["value"] and tags_tooltip_window is not None:
            return
        _hide_tags_tooltip()
        tags_tooltip_text["value"] = text
        tags_tooltip_window = show_popup_tooltip(
            owner=tags_tree,
            text=text,
            preferred_x=event.x_root + 12,
            preferred_y_bottom=event.y_root + 12,
            widget_top_y=event.y_root,
        )

    y_scroll = ttk.Scrollbar(list_frame, orient="vertical")
    y_scroll.grid(row=0, column=1, sticky="ns", pady=PAD_SM)

    def _sync_yview(*args: object) -> None:
        records_tree.yview(*args)
        tags_tree.yview(*args)

    def _on_main_yview(first: float, last: float) -> None:
        y_scroll.set(first, last)
        tags_tree.yview_moveto(first)

    def _on_tags_yview(first: float, last: float) -> None:
        y_scroll.set(first, last)
        records_tree.yview_moveto(first)

    y_scroll.configure(command=_sync_yview)
    records_tree.configure(yscrollcommand=_on_main_yview)
    tags_tree.configure(yscrollcommand=_on_tags_yview)

    x_scroll = ttk.Scrollbar(list_frame, orient="horizontal", command=records_tree.xview)
    x_scroll.grid(row=1, column=0, sticky="ew", padx=PAD_SM, pady=(6, PAD_SM))
    records_tree.configure(xscrollcommand=x_scroll.set)

    _syncing_selection = False

    def _sync_selection(source: ttk.Treeview, target: ttk.Treeview) -> None:
        nonlocal _syncing_selection
        if _syncing_selection:
            return
        _syncing_selection = True
        try:
            selection = source.selection()
            if not selection:
                target.selection_remove(target.selection())
                return
            iid = selection[0]
            if target.exists(iid):
                # Проверим, не выделен ли уже этот элемент в целевом дереве
                if target.selection() != (iid,):
                    target.selection_set(iid)
                    target.focus(iid)
                    target.see(iid)
        finally:
            _syncing_selection = False

    records_tree.bind("<<TreeviewSelect>>", lambda _event: _sync_selection(records_tree, tags_tree))
    tags_tree.bind("<<TreeviewSelect>>", lambda _event: _sync_selection(tags_tree, records_tree))
    tags_tree.bind("<Motion>", _show_tags_tooltip, add="+")
    tags_tree.bind("<Leave>", _hide_tags_tooltip, add="+")

    def save_record() -> None:
        date_str = date_entry.get().strip()
        if not date_str:
            show_error(tr("operations.error.date_required", "Укажите дату."))
            return
        try:
            from domain.validation import ensure_not_future, parse_ymd

            entered_date = parse_ymd(date_str)
            ensure_not_future(entered_date)
        except ValueError as error:
            show_error(
                tr(
                    "operations.error.invalid_date",
                    "Некорректная дата: {error}. Используйте формат ГГГГ-ММ-ДД.",
                    error=error,
                )
            )
            return

        amount_str = amount_entry.get().strip()
        if not amount_str:
            show_error(tr("operations.error.amount_required", "Укажите сумму."))
            return
        try:
            amount = float(amount_str)
        except ValueError:
            show_error(tr("operations.error.amount_number", "Сумма должна быть числом."))
            return

        currency = (currency_entry.get() or _base_currency_code()).strip()
        category = (category_combo.get() or "General").strip()
        description = description_entry.get().strip()
        raw_tags = tags_combo.get().strip()
        invalid_tags = find_numeric_only_tags(raw_tags)
        if invalid_tags:
            show_error(
                tr(
                    "operations.error.invalid_tag_numeric",
                    "Тег не должен состоять только из цифр: {tags}",
                    tags=", ".join(f'"{tag}"' for tag in invalid_tags),
                )
            )
            return
        tags = parse_tag_string(raw_tags)
        _committed_tags, active_fragment = _split_tag_input(raw_tags)
        wallet_id = operation_wallet_map.get(operation_wallet_var.get())
        if wallet_id is None:
            show_error(tr("operations.error.wallet_required", "Выберите кошелек."))
            return

        try:
            if type_combo.get() == income_label:
                context.controller.create_income(
                    date=date_str,
                    wallet_id=wallet_id,
                    amount=amount,
                    currency=currency,
                    category=category,
                    description=description,
                    tags=tags,
                )
                show_info(tr("operations.save_success.income", "Доход успешно добавлен."))
            else:
                context.controller.create_expense(
                    date=date_str,
                    wallet_id=wallet_id,
                    amount=amount,
                    currency=currency,
                    category=category,
                    description=description,
                    tags=tags,
                )
                show_info(tr("operations.save_success.expense", "Расход успешно добавлен."))

            existing_tags = {
                str(getattr(tag, "name", "") or ""): str(getattr(tag, "color", "") or "")
                for tag in _list_tags_safe()
            }
            active_tag_name = normalize_tag_name(active_fragment)
            if not active_tag_name and tags:
                active_tag_name = tags[-1]
            if active_tag_name and active_tag_name in tags:
                context.controller.set_tag_color(active_tag_name, selected_tag_color["value"])
            for tag_name in tags:
                if tag_name != active_tag_name and not existing_tags.get(tag_name):
                    context.controller.set_tag_color(tag_name, selected_tag_color["value"])

            amount_entry.delete(0, tk.END)
            category_combo.delete(0, tk.END)
            description_entry.delete(0, tk.END)
            tags_combo.delete(0, tk.END)
            _refresh_category_combo()
            _sync_tag_color_from_input()
            refresh_operation_views(context)
        except (DomainError, ValueError, TypeError, RuntimeError) as error:
            log_ui_error(logger, "UI_OPS_CREATE_RECORD_FAILED", error, wallet_id=wallet_id)
            show_error(
                tr(
                    "operations.error.save_failed",
                    "Не удалось сохранить операцию: {error}",
                    error=error,
                )
            )

    def _bind_focus_navigation(
        widgets: list[tk.Misc],
        *,
        submit_action: Callable[[], None] | None = None,
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
                widget.bind(
                    "<Return>", lambda _event: (_event.widget.invoke(), "break")[1], add="+"
                )
                widget.bind(
                    "<KP_Enter>", lambda _event: (_event.widget.invoke(), "break")[1], add="+"
                )
            elif callable(submit_action):
                widget.bind("<Return>", lambda _event: (submit_action(), "break")[1], add="+")
                widget.bind("<KP_Enter>", lambda _event: (submit_action(), "break")[1], add="+")

    creator_widgets = [
        date_entry,
        amount_entry,
        currency_entry,
        category_combo,
        description_entry,
        tags_combo,
        operation_wallet_menu,
    ]
    save_button = ttk.Button(
        form_frame,
        text=tr("common.save", "Сохранить"),
        style="Primary.TButton",
        command=save_record,
    )
    save_button.grid(row=8, column=0, columnspan=4, pady=8)
    _bind_focus_navigation([*creator_widgets, save_button], submit_action=save_record)

    def select_first_record() -> None:
        children = records_tree.get_children()
        if not children:
            return
        first = children[0]
        records_tree.selection_set(first)
        records_tree.focus(first)
        records_tree.see(first)

    def select_last_record() -> None:
        children = records_tree.get_children()
        if not children:
            return
        last = children[-1]
        records_tree.selection_set(last)
        records_tree.focus(last)
        records_tree.see(last)

    def delete_selected() -> None:
        selection = records_tree.selection()
        if not selection:
            show_error(tr("operations.error.select_first", "Сначала выберите запись."))
            return
        record_id = selection[0]
        repository_index = context._record_id_to_repo_index.get(record_id)
        if repository_index is None:
            show_error(tr("operations.error.unavailable", "Выбранная запись больше недоступна."))
            context._refresh_list()
            return
        try:
            transfer_id = context.controller.transfer_id_by_repository_index(repository_index)
            if transfer_id is not None:
                context.controller.delete_transfer(transfer_id)
                show_info(
                    tr("operations.transfer.deleted", "Перевод #{id} удален.", id=transfer_id)
                )
            elif context.controller.delete_record(repository_index):
                show_info(tr("operations.deleted", "Запись удалена."))
            else:
                show_error(tr("operations.error.delete_failed", "Не удалось удалить запись."))
                return
            refresh_operation_views(context)
            _refresh_category_combo()
        except (DomainError, ValueError, TypeError, RuntimeError) as error:
            log_ui_error(
                logger,
                "UI_OPS_DELETE_RECORD_FAILED",
                error,
                record_ui_id=record_id,
                repository_index=repository_index,
            )
            show_error(
                tr(
                    "operations.error.delete_failed_with_error",
                    "Не удалось удалить запись: {error}",
                    error=error,
                )
            )

    edit_panel_state: dict[str, Any] = {"panel": None}

    def inline_editor_active() -> bool:
        panel = edit_panel_state.get("panel")
        if panel is None:
            return False
        try:
            return bool(panel.winfo_exists())
        except (tk.TclError, RuntimeError, AttributeError):
            return False

    def edit_selected_transfer_inline(transfer_id: int) -> None:
        try:
            transfer = context.controller.get_transfer_for_edit(transfer_id)
        except (ValueError, TypeError, RuntimeError):
            show_error(
                tr(
                    "operations.transfer.error.edit_load_failed",
                    "Не удалось загрузить перевод для редактирования.",
                )
            )
            return

        if edit_panel_state["panel"] is not None:
            try:
                edit_panel_state["panel"].destroy()
            except (tk.TclError, RuntimeError):
                pass
            edit_panel_state["panel"] = None

        edit_panel = ttk.Frame(list_frame, style="InlinePanel.TFrame", padding=(8, 6))
        edit_panel.grid(row=4, column=0, columnspan=2, padx=6, sticky="ew")
        edit_panel_state["panel"] = edit_panel

        ttk.Label(edit_panel, text=tr("common.date", "Дата:")).grid(row=0, column=0, sticky="w")
        date_edit_entry = ttk.Entry(edit_panel)
        date_edit_entry.grid(row=0, column=1, sticky="ew")
        amount_edit_label = ttk.Label(
            edit_panel,
            text=_amount_edit_label_text(getattr(transfer, "currency", _base_currency_code())),
        )
        amount_edit_label.grid(row=1, column=0, sticky="w")
        amount_base_edit_entry = ttk.Entry(edit_panel)
        amount_base_edit_entry.grid(row=1, column=1, sticky="ew")
        Tooltip(amount_edit_label, amount_edit_tooltip_text)
        Tooltip(amount_base_edit_entry, amount_edit_tooltip_text)
        ttk.Label(edit_panel, text=tr("operations.transfer.from", "Из кошелька:")).grid(
            row=2, column=0, sticky="w"
        )
        from_wallet_var = tk.StringVar(value="")
        from_wallet_menu = ttk.Combobox(
            edit_panel,
            textvariable=from_wallet_var,
            values=[],
            state="readonly",
        )
        from_wallet_menu.grid(row=2, column=1, sticky="ew")
        ttk.Label(edit_panel, text=tr("operations.transfer.to", "В кошелек:")).grid(
            row=3, column=0, sticky="w"
        )
        to_wallet_var = tk.StringVar(value="")
        to_wallet_menu = ttk.Combobox(
            edit_panel,
            textvariable=to_wallet_var,
            values=[],
            state="readonly",
        )
        to_wallet_menu.grid(row=3, column=1, sticky="ew")
        ttk.Label(edit_panel, text=tr("operations.transfer.description", "Описание:")).grid(
            row=4, column=0, sticky="w"
        )
        description_edit_entry = ttk.Entry(edit_panel)
        description_edit_entry.grid(row=4, column=1, sticky="ew")
        edit_panel.grid_columnconfigure(1, weight=1)

        date_value = (
            transfer.date.isoformat() if hasattr(transfer.date, "isoformat") else str(transfer.date)
        )
        date_edit_entry.insert(0, date_value)
        if _is_kzt_currency(getattr(transfer, "currency", _base_currency_code())):
            amount_value = float(transfer.amount_original or transfer.amount_base or 0.0)
        else:
            amount_value = float(transfer.amount_base or 0.0)
        amount_base_edit_entry.insert(0, f"{amount_value:.2f}")
        description_edit_entry.insert(0, transfer.description)

        wallet_edit_map: dict[str, int] = {
            f"[{wallet.id}] {wallet.name} ({wallet.currency})": wallet.id
            for wallet in context.controller.load_active_wallets()
        }
        wallet_labels = list(wallet_edit_map.keys()) or [""]
        from_wallet_menu["values"] = wallet_labels
        to_wallet_menu["values"] = wallet_labels
        from_wallet_var.set(
            next(
                (
                    label
                    for label, wallet_id in wallet_edit_map.items()
                    if int(wallet_id) == int(transfer.from_wallet_id)
                ),
                wallet_labels[0],
            )
        )
        to_wallet_var.set(
            next(
                (
                    label
                    for label, wallet_id in wallet_edit_map.items()
                    if int(wallet_id) == int(transfer.to_wallet_id)
                ),
                wallet_labels[0],
            )
        )

        def cancel_edit() -> None:
            if edit_panel_state["panel"] is not None:
                safe_destroy(edit_panel_state["panel"])
                edit_panel_state["panel"] = None

        def save_edit() -> None:
            new_date = date_edit_entry.get().strip()
            if not new_date:
                show_error(tr("operations.transfer.error.date_required", "Укажите дату перевода."))
                return
            try:
                new_amount_base = float(amount_base_edit_entry.get().strip())
            except ValueError:
                show_error(tr("operations.error.amount_number", "Сумма должна быть числом."))
                return
            new_from_wallet_id = wallet_edit_map.get(from_wallet_var.get())
            new_to_wallet_id = wallet_edit_map.get(to_wallet_var.get())
            if new_from_wallet_id is None or new_to_wallet_id is None:
                show_error(
                    tr(
                        "operations.transfer.error.wallets_required",
                        "Выберите кошелек отправителя и получателя.",
                    )
                )
                return
            try:
                context.controller.update_transfer_inline(
                    transfer_id,
                    new_date=new_date,
                    new_from_wallet_id=new_from_wallet_id,
                    new_to_wallet_id=new_to_wallet_id,
                    new_description=description_edit_entry.get().strip(),
                    new_amount_base=new_amount_base,
                )
                show_info(tr("operations.transfer.updated", "Перевод обновлен."))
                refresh_operation_views(context)
                _refresh_category_combo()
                cancel_edit()
            except (DomainError, ValueError, TypeError, RuntimeError) as error:
                log_ui_error(
                    logger,
                    "UI_OPS_EDIT_TRANSFER_FAILED",
                    error,
                    transfer_id=transfer_id,
                    new_from_wallet_id=new_from_wallet_id,
                    new_to_wallet_id=new_to_wallet_id,
                    new_amount_base=new_amount_base,
                )
                show_error(
                    tr(
                        "operations.transfer.error.update_failed",
                        "Не удалось обновить перевод: {error}",
                        error=error,
                    )
                )

        edit_buttons = ttk.Frame(edit_panel, style="InlinePanel.TFrame")
        edit_buttons.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        edit_buttons.grid_columnconfigure(0, weight=1)
        edit_buttons.grid_columnconfigure(1, weight=1)
        save_button = ttk.Button(
            edit_buttons,
            text=tr("common.save", "Сохранить"),
            command=save_edit,
            style="Primary.TButton",
        )
        save_button.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        cancel_button = ttk.Button(
            edit_buttons,
            text=tr("common.cancel", "Отмена"),
            command=cancel_edit,
        )
        cancel_button.grid(row=0, column=1, sticky="ew", padx=(4, 0))
        for widget in (
            date_edit_entry,
            amount_base_edit_entry,
            from_wallet_menu,
            to_wallet_menu,
            description_edit_entry,
            save_button,
            cancel_button,
        ):
            widget.bind("<Escape>", lambda _event: (cancel_edit(), "break")[1], add="+")
        date_edit_entry.bind("<Return>", lambda _event: (save_edit(), "break")[1], add="+")
        amount_base_edit_entry.bind("<Return>", lambda _event: (save_edit(), "break")[1], add="+")
        to_wallet_menu.bind("<Return>", lambda _event: (save_edit(), "break")[1], add="+")
        description_edit_entry.bind("<Return>", lambda _event: (save_edit(), "break")[1], add="+")
        date_edit_entry.focus_set()
        date_edit_entry.selection_range(0, tk.END)

    def edit_selected_record_inline() -> None:
        selection = records_tree.selection()
        if not selection:
            show_error(tr("operations.error.select_first", "Сначала выберите запись."))
            return

        ui_record_id = selection[0]
        domain_record_id = context._record_id_to_domain_id.get(ui_record_id)
        if domain_record_id is None:
            show_error(tr("operations.error.edit_forbidden", "Эту запись нельзя редактировать."))
            return

        try:
            record = context.controller.get_record_for_edit(domain_record_id)
        except (ValueError, TypeError, RuntimeError):
            show_error(
                tr(
                    "operations.error.edit_load_failed",
                    "Не удалось загрузить запись для редактирования.",
                )
            )
            return

        if record.transfer_id is not None:
            edit_selected_transfer_inline(int(record.transfer_id))
            return
        if str(getattr(record, "category", "") or "").strip().lower() == "transfer":
            show_error(
                tr(
                    "operations.error.transfer_row_edit_forbidden",
                    "Строки перевода редактировать нельзя.",
                )
            )
            return

        if edit_panel_state["panel"] is not None:
            try:
                edit_panel_state["panel"].destroy()
            except (tk.TclError, RuntimeError):
                pass
            edit_panel_state["panel"] = None

        edit_panel = ttk.Frame(list_frame, style="InlinePanel.TFrame", padding=(8, 6))
        edit_panel.grid(row=3, column=0, columnspan=2, padx=6, sticky="ew")
        edit_panel_state["panel"] = edit_panel

        amount_edit_label = ttk.Label(
            edit_panel,
            text=_amount_edit_label_text(getattr(record, "currency", _base_currency_code())),
        )
        amount_edit_label.grid(row=0, column=0, sticky="w")
        amount_entry = ttk.Entry(edit_panel)
        amount_entry.grid(row=0, column=1, sticky="ew")
        Tooltip(amount_edit_label, amount_edit_tooltip_text)
        Tooltip(amount_entry, amount_edit_tooltip_text)
        ttk.Label(edit_panel, text=tr("common.date", "Дата:")).grid(row=1, column=0, sticky="w")
        date_edit_entry = ttk.Entry(edit_panel)
        date_edit_entry.grid(row=1, column=1, sticky="ew")
        ttk.Label(edit_panel, text=tr("common.wallet", "Кошелек:")).grid(
            row=2, column=0, sticky="w"
        )
        wallet_edit_var = tk.StringVar(value="")
        wallet_edit_menu = ttk.Combobox(
            edit_panel,
            textvariable=wallet_edit_var,
            values=[],
            state="readonly",
        )
        wallet_edit_menu.grid(row=2, column=1, sticky="ew")
        ttk.Label(edit_panel, text=tr("common.category", "Категория:")).grid(
            row=3, column=0, sticky="w"
        )
        category_edit_combo = ttk.Combobox(edit_panel, state="normal")
        category_edit_combo.grid(row=3, column=1, sticky="ew")
        ttk.Label(edit_panel, text=tr("common.description", "Описание:")).grid(
            row=4, column=0, sticky="w"
        )
        description_edit_entry = ttk.Entry(edit_panel)
        description_edit_entry.grid(row=4, column=1, sticky="ew")
        ttk.Label(edit_panel, text=tr("common.tags", "Теги:")).grid(row=5, column=0, sticky="w")
        tags_edit_combo = ttk.Combobox(edit_panel, state="normal")
        tags_edit_combo.grid(row=5, column=1, sticky="ew")
        edit_panel.grid_columnconfigure(1, weight=1)
        edit_tags_popup_state: dict[str, Any] = {"window": None, "listbox": None, "items": []}
        edit_tag_selection_state: dict[str, Any] = {"committed": (), "fragment": ""}

        def _hide_edit_tags_popup(_event: object | None = None) -> None:
            window = edit_tags_popup_state.get("window")
            if window is not None:
                try:
                    window.destroy()
                except tk.TclError:
                    pass
            edit_tags_popup_state["window"] = None
            edit_tags_popup_state["listbox"] = None
            edit_tags_popup_state["items"] = []

        def _split_edit_tag_input(raw_value: str) -> tuple[tuple[str, ...], str]:
            parts = str(raw_value or "").split(",")
            committed = parse_tag_string(",".join(parts[:-1])) if len(parts) > 1 else ()
            fragment = parts[-1].strip() if parts else ""
            return committed, fragment

        def _remember_edit_tag_input_state(
            raw_value: str | None = None,
        ) -> tuple[tuple[str, ...], str]:
            committed, fragment = _split_edit_tag_input(
                tags_edit_combo.get() if raw_value is None else raw_value
            )
            edit_tag_selection_state["committed"] = committed
            edit_tag_selection_state["fragment"] = fragment
            return committed, fragment

        def _build_edit_tag_suggestions(raw_value: str) -> list[Any]:
            committed, fragment = _split_edit_tag_input(raw_value)
            committed_set = set(committed)
            normalized_fragment = normalize_tag_name(fragment)
            suggestions: list[Any] = []
            for tag in _sorted_tags_by_popularity():
                tag_name = str(getattr(tag, "name", "") or "")
                if not tag_name or tag_name in committed_set:
                    continue
                if normalized_fragment and not tag_name.startswith(normalized_fragment):
                    continue
                suggestions.append(tag)
            return suggestions

        def _apply_edit_tag_selection(
            tag_name: str,
            *,
            committed_override: tuple[str, ...] | None = None,
        ) -> None:
            committed = (
                tuple(committed_override)
                if committed_override is not None
                else tuple(edit_tag_selection_state.get("committed", ()) or ())
            )
            next_tags = [*committed, tag_name][:MAX_TAGS_PER_RECORD]
            text = ", ".join(next_tags)
            if len(next_tags) < MAX_TAGS_PER_RECORD:
                text = f"{text}, "
            tags_edit_combo.delete(0, tk.END)
            tags_edit_combo.insert(0, text)
            _remember_edit_tag_input_state(text)
            _hide_edit_tags_popup()
            tags_edit_combo.focus_set()
            tags_edit_combo.icursor(tk.END)

        def _show_edit_tags_popup(*, focus_listbox: bool = False) -> None:
            _remember_edit_tag_input_state()
            suggestions = _build_edit_tag_suggestions(tags_edit_combo.get())
            tags_edit_combo["values"] = [tag.name for tag in suggestions]
            if not suggestions:
                _hide_edit_tags_popup()
                return
            _hide_edit_tags_popup()
            popup = tk.Toplevel(edit_panel)
            popup.wm_overrideredirect(True)
            popup.configure(bg=palette.border_soft)
            popup.transient(edit_panel.winfo_toplevel())
            x = tags_edit_combo.winfo_rootx()
            y = tags_edit_combo.winfo_rooty() + tags_edit_combo.winfo_height() + 2
            width = max(tags_edit_combo.winfo_width(), 220)
            popup.wm_geometry(f"{width}x160+{x}+{y}")
            listbox = tk.Listbox(
                popup,
                activestyle="none",
                borderwidth=0,
                highlightthickness=0,
                font=(FONT_FAMILY, 10),
                selectmode=tk.SINGLE,
                bg=palette.surface_elevated,
                fg=palette.text_primary,
                selectbackground=palette.accent_blue,
                selectforeground=palette.surface_elevated,
            )
            listbox.pack(fill="both", expand=True, padx=1, pady=1)
            for index, tag in enumerate(suggestions):
                listbox.insert(tk.END, f"#{tag.name}")
                listbox.itemconfig(
                    index,
                    fg=str(getattr(tag, "color", "") or palette.text_primary),
                    bg=palette.surface_elevated,
                )
            listbox.selection_set(0)
            listbox.activate(0)
            edit_tags_popup_state["window"] = popup
            edit_tags_popup_state["listbox"] = listbox
            edit_tags_popup_state["items"] = suggestions

            def _confirm_selection(_event: tk.Event | None = None) -> str:
                selected = listbox.curselection()
                if not selected:
                    return "break"
                chosen = suggestions[int(selected[0])]
                _apply_edit_tag_selection(str(getattr(chosen, "name", "") or ""))
                return "break"

            listbox.bind("<Return>", _confirm_selection, add="+")
            listbox.bind("<Double-Button-1>", _confirm_selection, add="+")
            listbox.bind("<ButtonRelease-1>", _confirm_selection, add="+")
            listbox.bind("<Escape>", lambda _event: (_hide_edit_tags_popup(), "break")[1], add="+")
            popup.bind("<FocusOut>", _hide_edit_tags_popup, add="+")
            if focus_listbox:
                popup.after(0, listbox.focus_set)

        def _prepare_edit_native_tag_dropdown() -> None:
            _remember_edit_tag_input_state()
            suggestions = _build_edit_tag_suggestions(tags_edit_combo.get())
            tags_edit_combo["values"] = [tag.name for tag in suggestions]

        def _on_edit_tags_key_release(event: tk.Event | None = None) -> None:
            if event is not None and event.keysym in {"Up", "Down", "Return", "Escape", "Tab"}:
                return
            _remember_edit_tag_input_state()
            _show_edit_tags_popup()

        def _on_edit_tags_down(_event: tk.Event | None = None) -> str:
            _show_edit_tags_popup(focus_listbox=True)
            listbox = edit_tags_popup_state.get("listbox")
            if listbox is not None:
                listbox.focus_set()
            return "break"

        def _on_edit_tags_combobox_selected(_event: tk.Event | None = None) -> str:
            chosen = normalize_tag_name(tags_edit_combo.get())
            if not chosen:
                return "break"
            committed = tuple(edit_tag_selection_state.get("committed", ()) or ())
            if chosen in committed:
                _apply_edit_tag_selection(
                    chosen,
                    committed_override=tuple(tag for tag in committed if tag != chosen),
                )
            else:
                _apply_edit_tag_selection(chosen, committed_override=committed)
            return "break"

        tags_edit_combo.configure(postcommand=_prepare_edit_native_tag_dropdown)
        tags_edit_combo.bind("<KeyRelease>", _on_edit_tags_key_release, add="+")
        tags_edit_combo.bind("<Down>", _on_edit_tags_down, add="+")
        tags_edit_combo.bind("<<ComboboxSelected>>", _on_edit_tags_combobox_selected, add="+")
        tags_edit_combo.bind(
            "<Button-1>",
            lambda _event: tags_edit_combo.after(0, _show_edit_tags_popup),
            add="+",
        )
        tags_edit_combo.bind(
            "<FocusOut>",
            lambda _event: tags_edit_combo.after(100, _hide_edit_tags_popup),
            add="+",
        )

        # Fill the fields with post data
        if _is_kzt_currency(getattr(record, "currency", _base_currency_code())):
            amount_value = float(record.amount_original or record.amount_base or 0.0)
        else:
            amount_value = float(record.amount_base or 0.0)
        amount_entry.insert(0, f"{amount_value:.2f}")
        date_value = (
            record.date.isoformat() if hasattr(record.date, "isoformat") else str(record.date)
        )
        date_edit_entry.insert(0, date_value)
        try:
            if record.type == "income":
                category_edit_combo["values"] = context.controller.get_income_categories()
            elif record.type == "expense":
                category_edit_combo["values"] = context.controller.get_expense_categories()
            else:
                category_edit_combo["values"] = (
                    context.controller.get_mandatory_expense_categories()
                )
        except (ValueError, RuntimeError):
            pass
        category_edit_combo.insert(0, str(record.category or ""))
        description_edit_entry.insert(0, str(record.description or ""))
        tags_edit_combo.insert(0, ", ".join(tuple(getattr(record, "tags", ()) or ())))
        _remember_edit_tag_input_state(tags_edit_combo.get())

        wallet_edit_map: dict[str, int] = {
            f"[{wallet.id}] {wallet.name} ({wallet.currency})": wallet.id
            for wallet in context.controller.load_wallets()
        }
        wallet_labels = list(wallet_edit_map.keys()) or [""]
        wallet_edit_menu["values"] = wallet_labels
        current_wallet_label = next(
            (label for label, wid in wallet_edit_map.items() if int(wid) == int(record.wallet_id)),
            wallet_labels[0],
        )
        wallet_edit_var.set(current_wallet_label)

        def save_edit() -> None:
            try:
                new_amount_base = float(amount_entry.get().strip())
            except ValueError:
                show_error(tr("operations.error.amount_number", "Сумма должна быть числом."))
                return
            new_date = date_edit_entry.get().strip()
            if not new_date:
                show_error(tr("operations.error.date_required", "Укажите дату."))
                return
            new_category = category_edit_combo.get().strip()
            if not new_category:
                show_error(tr("operations.error.category_required", "Укажите категорию."))
                return
            new_wallet_id = wallet_edit_map.get(wallet_edit_var.get())
            if new_wallet_id is None:
                show_error(tr("operations.error.wallet_required", "Выберите кошелек."))
                return
            invalid_tags = find_numeric_only_tags(tags_edit_combo.get().strip())
            if invalid_tags:
                show_error(
                    tr(
                        "operations.error.invalid_tag_numeric",
                        "Тег не должен состоять только из цифр: {tags}",
                        tags=", ".join(f'"{tag}"' for tag in invalid_tags),
                    )
                )
                return
            try:
                context.controller.update_record_inline(
                    domain_record_id,
                    new_amount_base=new_amount_base,
                    new_category=new_category,
                    new_description=description_edit_entry.get().strip(),
                    new_date=new_date,
                    new_wallet_id=new_wallet_id,
                    new_tags=tags_edit_combo.get().strip(),
                )
                show_info(tr("operations.updated", "Запись обновлена."))
                _sync_tag_color_from_input()
                refresh_operation_views(context)
                _refresh_category_combo()
                cancel_edit()
            except (DomainError, ValueError, TypeError, RuntimeError) as error:
                log_ui_error(
                    logger,
                    "UI_OPS_EDIT_RECORD_FAILED",
                    error,
                    record_id=domain_record_id,
                    new_wallet_id=new_wallet_id,
                )
                show_error(
                    tr(
                        "operations.error.update_failed",
                        "Не удалось обновить запись: {error}",
                        error=error,
                    )
                )

        def cancel_edit() -> None:
            if edit_panel_state["panel"] is not None:
                safe_destroy(edit_panel_state["panel"])
                edit_panel_state["panel"] = None

        edit_buttons = ttk.Frame(edit_panel, style="InlinePanel.TFrame")
        edit_buttons.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        edit_buttons.grid_columnconfigure(0, weight=1)
        edit_buttons.grid_columnconfigure(1, weight=1)
        save_button = ttk.Button(
            edit_buttons,
            text=tr("common.save", "Сохранить"),
            style="Primary.TButton",
            command=save_edit,
        )
        save_button.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        cancel_button = ttk.Button(
            edit_buttons, text=tr("common.cancel", "Отмена"), command=cancel_edit
        )
        cancel_button.grid(row=0, column=1, sticky="ew", padx=(6, 0))

        navigation_widgets: list[tk.Misc] = [
            amount_entry,
            date_edit_entry,
            wallet_edit_menu,
            category_edit_combo,
            description_edit_entry,
            tags_edit_combo,
            save_button,
            cancel_button,
        ]

        def _focus_relative(index: int) -> str:
            navigation_widgets[index % len(navigation_widgets)].focus_set()
            return "break"

        def _bind_editor_navigation(widget: tk.Misc, index: int) -> None:
            widget.bind("<Up>", lambda _event, i=index - 1: _focus_relative(i), add="+")
            widget.bind("<Down>", lambda _event, i=index + 1: _focus_relative(i), add="+")
            if isinstance(widget, ttk.Button):
                widget.bind("<Left>", lambda _event, i=index - 1: _focus_relative(i), add="+")
                widget.bind("<Right>", lambda _event, i=index + 1: _focus_relative(i), add="+")
                widget.bind(
                    "<Return>", lambda _event: (_event.widget.invoke(), "break")[1], add="+"
                )
                widget.bind(
                    "<KP_Enter>", lambda _event: (_event.widget.invoke(), "break")[1], add="+"
                )
            else:
                widget.bind("<Return>", lambda _event: (save_edit(), "break")[1], add="+")
                widget.bind("<KP_Enter>", lambda _event: (save_edit(), "break")[1], add="+")
            widget.bind("<Escape>", lambda _event: (cancel_edit(), "break")[1], add="+")

        for index, widget in enumerate(navigation_widgets):
            _bind_editor_navigation(widget, index)

        amount_entry.focus_set()

    def delete_all() -> None:
        confirm = ask_confirm(
            tr(
                "operations.delete_all.confirm",
                "Удалить все записи? Это действие нельзя отменить.",
            ),
            title=tr("operations.delete_all.title", "Подтвердите удаление"),
        )
        if confirm:
            context.controller.delete_all_records()
            show_info(tr("operations.deleted_all_done", "Все записи удалены."))
            refresh_operation_views(context)
            _refresh_category_combo()

    wallet_id_map: dict[str, int] = {}

    transfer_card = create_card_section(
        paned,
        tr("operations.transfer", "Перевод между кошельками"),
    )
    paned.add(transfer_card, weight=1)
    transfer_frame = transfer_card.winfo_children()[-1]
    transfer_frame.grid_columnconfigure(1, weight=1)

    ttk.Label(transfer_frame, text=tr("operations.transfer.from", "Из кошелька:")).grid(
        row=0, column=0, sticky="w", padx=PAD_SM, pady=PAD_XS
    )
    transfer_from_var = tk.StringVar(value="")
    transfer_from_menu = ttk.Combobox(
        transfer_frame,
        textvariable=transfer_from_var,
        values=[],
        state="readonly",
    )
    transfer_from_menu.grid(row=0, column=1, sticky="ew", padx=PAD_SM, pady=PAD_XS)

    ttk.Label(transfer_frame, text=tr("operations.transfer.to", "В кошелек:")).grid(
        row=1, column=0, sticky="w", padx=PAD_SM, pady=PAD_XS
    )
    transfer_to_var = tk.StringVar(value="")
    transfer_to_menu = ttk.Combobox(
        transfer_frame,
        textvariable=transfer_to_var,
        values=[],
        state="readonly",
    )
    transfer_to_menu.grid(row=1, column=1, sticky="ew", padx=PAD_SM, pady=PAD_XS)

    ttk.Label(transfer_frame, text=tr("common.date", "Дата:")).grid(
        row=2, column=0, sticky="w", padx=PAD_SM, pady=PAD_XS
    )
    transfer_date_entry = ttk.Entry(transfer_frame)
    transfer_date_entry.grid(row=2, column=1, sticky="ew", padx=PAD_SM, pady=PAD_XS)
    transfer_date_entry.insert(0, date.today().isoformat())

    ttk.Label(transfer_frame, text=tr("common.amount", "Сумма:")).grid(
        row=3, column=0, sticky="w", padx=PAD_SM, pady=PAD_XS
    )
    transfer_amount_entry = ttk.Entry(transfer_frame)
    transfer_amount_entry.grid(row=3, column=1, sticky="ew", padx=PAD_SM, pady=PAD_XS)

    ttk.Label(transfer_frame, text=tr("common.currency", "Валюта:")).grid(
        row=4, column=0, sticky="w", padx=PAD_SM, pady=PAD_XS
    )
    transfer_currency_entry = ttk.Entry(transfer_frame)
    transfer_currency_entry.insert(0, _base_currency_code())
    transfer_currency_entry.grid(row=4, column=1, sticky="ew", padx=PAD_SM, pady=PAD_XS)

    ttk.Label(transfer_frame, text=tr("operations.transfer.commission", "Комиссия:")).grid(
        row=5, column=0, sticky="w", padx=PAD_SM, pady=PAD_XS
    )
    transfer_commission_entry = ttk.Entry(transfer_frame)
    transfer_commission_entry.insert(0, "0")
    transfer_commission_entry.grid(row=5, column=1, sticky="ew", padx=PAD_SM, pady=PAD_XS)

    ttk.Label(
        transfer_frame, text=tr("operations.transfer.commission_currency", "Валюта комиссии:")
    ).grid(row=6, column=0, sticky="w", padx=PAD_SM, pady=PAD_XS)
    transfer_commission_currency_entry = ttk.Entry(transfer_frame)
    transfer_commission_currency_entry.insert(0, _base_currency_code())
    transfer_commission_currency_entry.grid(row=6, column=1, sticky="ew", padx=PAD_SM, pady=PAD_XS)

    ttk.Label(transfer_frame, text=tr("common.description", "Описание:")).grid(
        row=7, column=0, sticky="w", padx=PAD_SM, pady=PAD_XS
    )
    transfer_description_entry = ttk.Entry(transfer_frame)
    transfer_description_entry.grid(row=7, column=1, sticky="ew", padx=PAD_SM, pady=PAD_XS)

    def refresh_transfer_wallet_menus() -> None:
        nonlocal wallet_id_map
        wallets = context.controller.load_active_wallets()
        wallet_id_map = {
            f"[{wallet.id}] {wallet.name} ({wallet.currency})": wallet.id for wallet in wallets
        }
        labels = list(wallet_id_map.keys()) or [""]

        for combo_widget, var in (
            (transfer_from_menu, transfer_from_var),
            (transfer_to_menu, transfer_to_var),
        ):
            combo_widget["values"] = labels
            if not var.get() or var.get() not in wallet_id_map:
                var.set(labels[0])

        if len(labels) > 1 and transfer_to_var.get() == transfer_from_var.get():
            transfer_to_var.set(labels[1])

    def create_transfer() -> None:
        from_wallet_id = wallet_id_map.get(transfer_from_var.get())
        to_wallet_id = wallet_id_map.get(transfer_to_var.get())
        if from_wallet_id is None or to_wallet_id is None:
            show_error(
                tr(
                    "operations.transfer.error.wallets_required",
                    "Выберите кошелек отправителя и получателя.",
                )
            )
            return

        date_str = transfer_date_entry.get().strip()
        if not date_str:
            show_error(tr("operations.transfer.error.date_required", "Укажите дату перевода."))
            return
        try:
            from domain.validation import ensure_not_future, parse_ymd

            entered_date = parse_ymd(date_str)
            ensure_not_future(entered_date)
        except ValueError as error:
            show_error(
                tr(
                    "operations.error.invalid_date",
                    "Некорректная дата: {error}. Используйте формат ГГГГ-ММ-ДД.",
                    error=error,
                )
            )
            return

        amount_str = transfer_amount_entry.get().strip()
        if not amount_str:
            show_error(tr("operations.transfer.error.amount_required", "Укажите сумму перевода."))
            return

        try:
            transfer_amount = float(amount_str)
            commission_amount = float((transfer_commission_entry.get() or "0").strip())
        except ValueError:
            show_error(
                tr(
                    "operations.transfer.error.amount_number",
                    "Сумма перевода и комиссия должны быть числами.",
                )
            )
            return

        try:
            transfer_id = context.controller.create_transfer(
                from_wallet_id=from_wallet_id,
                to_wallet_id=to_wallet_id,
                transfer_date=date_str,
                amount=transfer_amount,
                currency=(transfer_currency_entry.get() or _base_currency_code()).strip(),
                description=transfer_description_entry.get().strip(),
                commission_amount=commission_amount,
                commission_currency=(transfer_commission_currency_entry.get() or "").strip(),
            )
            show_info(
                tr("operations.transfer.created", "Перевод создан (id={id}).", id=transfer_id)
            )
            transfer_amount_entry.delete(0, tk.END)
            transfer_description_entry.delete(0, tk.END)
            transfer_commission_entry.delete(0, tk.END)
            transfer_commission_entry.insert(0, "0")
            refresh_operation_views(context)
            _refresh_category_combo()
        except (DomainError, ValueError, TypeError, RuntimeError) as error:
            log_ui_error(
                logger,
                "UI_OPS_CREATE_TRANSFER_FAILED",
                error,
                from_wallet_id=from_wallet_id,
                to_wallet_id=to_wallet_id,
            )
            show_error(
                tr(
                    "operations.transfer.error.create_failed",
                    "Не удалось создать перевод: {error}",
                    error=error,
                )
            )

    transfer_creator_widgets = [
        transfer_from_menu,
        transfer_to_menu,
        transfer_date_entry,
        transfer_amount_entry,
        transfer_currency_entry,
        transfer_commission_entry,
        transfer_commission_currency_entry,
        transfer_description_entry,
    ]
    transfer_create_button = ttk.Button(
        transfer_card,
        text=tr("operations.transfer.create", "Создать перевод"),
        command=create_transfer,
        style="Primary.TButton",
    )
    transfer_create_button.grid(row=8, column=0, columnspan=2, pady=6)
    _bind_focus_navigation(
        [*transfer_creator_widgets, transfer_create_button], submit_action=create_transfer
    )
    refresh_transfer_wallet_menus()

    import_mode_keys = [
        "operations.mode.replace",
        "operations.mode.current_rate",
        "operations.mode.legacy",
    ]
    import_mode_labels = [
        tr("operations.mode.replace", "Полная замена"),
        tr("operations.mode.current_rate", "По текущему курсу"),
        tr("operations.mode.legacy", "Наследуемый импорт"),
    ]
    import_mode_label_var = tk.StringVar(value=import_mode_labels[0])
    import_mode_key_var = tk.StringVar(value=import_mode_keys[0])
    import_format_var = tk.StringVar(value="CSV")

    def import_records_data() -> None:
        policy = context._import_policy_from_ui(import_mode_key_var.get())
        fmt = import_format_var.get()
        cfg = import_formats.get(fmt)
        if not cfg:
            show_error(
                tr(
                    "operations.error.import_format",
                    "Неподдерживаемый формат импорта: {fmt}",
                    fmt=fmt,
                )
            )
            return

        filepath = filedialog.askopenfilename(
            defaultextension=cfg["ext"],
            filetypes=[(f"{fmt} files", f"*{cfg['ext']}"), ("All files", "*.*")],
            title=tr(
                "operations.import.select_file",
                "Выберите файл {format} для импорта",
                format=cfg["desc"],
            ),
        )
        if not filepath:
            return

        if policy == ImportPolicy.CURRENT_RATE:
            show_warning(
                tr(
                    "operations.import.current_rate.body",
                    "В режиме CURRENT_RATE курсы валют будут зафиксированы на момент импорта.",
                ),
                title=tr("operations.import.current_rate.title", "Импорт по текущему курсу"),
            )

        def preview_task() -> ImportResult:
            return context.controller.import_records(fmt, filepath, policy, dry_run=True)

        def commit_task() -> ImportResult:
            return context.controller.import_records(fmt, filepath, policy, dry_run=False)

        def on_commit_success(result: ImportResult) -> None:
            details = ""
            if result.skipped or result.errors:
                details = f"\nПропущено строк: {result.skipped}.\nПервые ошибки:\n- " + "\n- ".join(
                    result.errors[:5]
                )
            show_info(
                tr(
                    "operations.import.success",
                    "Импортировано записей: {count} ({format}).\nТекущие записи были заменены.",
                    count=result.imported,
                    format=cfg["desc"],
                )
                + details,
                title=tr("common.done", "Готово"),
            )
            refresh_operation_views(context)
            _refresh_category_combo()

        def on_error(exc: BaseException) -> None:
            if isinstance(exc, FileNotFoundError):
                show_error(
                    tr("common.file_not_found", "Файл не найден: {filepath}", filepath=filepath)
                )
                return
            show_error(
                tr(
                    "operations.import.error",
                    "Не удалось импортировать {format}: {error}",
                    format=cfg["desc"],
                    error=exc,
                )
            )

        def on_preview_success(preview: ImportResult) -> None:
            confirmed = show_import_preview_dialog(
                parent=parent,
                filepath=filepath,
                policy_label=import_mode_label_var.get(),
                preview=preview,
                force=False,
            )
            if not confirmed:
                return
            context._run_background(
                commit_task,
                on_success=on_commit_success,
                on_error=on_error,
                busy_message=tr(
                    "operations.busy.import",
                    "Импортируем {format}...",
                    format=cfg["desc"],
                ),
            )

        context._run_background(
            preview_task,
            on_success=on_preview_success,
            on_error=on_error,
            busy_message=tr(
                "operations.busy.validate",
                "Проверяем импорт {format}...",
                format=cfg["desc"],
            ),
        )

    def export_records_data() -> None:
        fmt = import_format_var.get()
        cfg = import_formats.get(fmt)
        if not cfg or fmt == "JSON":
            show_error(
                tr(
                    "operations.export.unsupported",
                    "Этот формат не поддерживается для экспорта операций.",
                )
            )
            return
        filepath = filedialog.asksaveasfilename(
            defaultextension=cfg["ext"],
            filetypes=[(f"{cfg['desc']} files", f"*{cfg['ext']}"), ("All files", "*.*")],
            title=tr(
                "operations.export.save_as", "Сохранить операции как {format}", format=cfg["desc"]
            ),
        )
        if not filepath:
            return

        records = context.repository.load_all()
        transfers = context.repository.load_transfers()

        def task() -> None:
            from gui.exporters import export_records

            export_records(records, filepath, fmt.lower(), transfers=transfers)

        def on_success(_: Any) -> None:
            show_info(
                tr(
                    "operations.export.success",
                    "Операции экспортированы в:\n{filepath}",
                    filepath=filepath,
                )
            )
            open_in_file_manager(os.path.dirname(filepath))

        context._run_background(
            task,
            on_success=on_success,
            busy_message=tr(
                "operations.busy.export",
                "Экспортируем {format}...",
                format=cfg["desc"],
            ),
        )

    actions_frame = ttk.Frame(list_frame)
    actions_frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=6)
    actions_frame.grid_columnconfigure(0, weight=1)
    actions_frame.grid_columnconfigure(1, weight=1)

    primary_actions = ttk.Frame(actions_frame)
    primary_actions.grid(row=0, column=0, sticky="ew", pady=0, padx=(0, 6))
    import_actions = ttk.Frame(actions_frame)
    import_actions.grid(row=0, column=1, sticky="ew", pady=0, padx=(6, 0))
    for idx in range(4):
        primary_actions.grid_columnconfigure(idx, weight=1)
    for idx in range(6):
        import_actions.grid_columnconfigure(idx, weight=1)

    ttk.Button(
        primary_actions,
        text=tr("common.delete", "Удалить"),
        command=delete_selected,
    ).grid(row=0, column=0, sticky="ew", padx=(0, 6))
    ttk.Button(
        primary_actions,
        text=tr("common.edit", "Редактировать"),
        command=edit_selected_record_inline,
    ).grid(row=0, column=1, sticky="ew", padx=6)
    ttk.Button(
        primary_actions,
        text=tr("common.refresh", "Обновить"),
        command=context._refresh_list,
    ).grid(row=0, column=2, sticky="ew", padx=6)
    ttk.Button(
        primary_actions,
        text=tr("operations.delete_all", "Удалить все"),
        command=delete_all,
    ).grid(row=0, column=3, sticky="ew", padx=(6, 0))

    ttk.Label(import_actions, text=tr("common.format", "Формат:")).grid(row=0, column=0, sticky="w")
    ttk.Combobox(
        import_actions,
        textvariable=import_format_var,
        values=["CSV", "XLSX"],
        state="readonly",
    ).grid(row=0, column=1, sticky="ew", padx=(6, 8))
    ttk.Label(import_actions, text=tr("common.mode", "Режим:")).grid(row=0, column=2, sticky="w")
    import_mode_combo = ttk.Combobox(
        import_actions,
        textvariable=import_mode_label_var,
        values=import_mode_labels,
        state="readonly",
    )
    import_mode_combo.grid(row=0, column=3, sticky="ew", padx=(6, 8))

    def _sync_import_mode_key(_event: Any | None = None) -> None:
        idx = import_mode_combo.current()
        if idx < 0:
            idx = 0
        import_mode_key_var.set(import_mode_keys[idx])

    import_mode_combo.bind("<<ComboboxSelected>>", _sync_import_mode_key)
    _sync_import_mode_key()
    ttk.Button(
        import_actions,
        text=tr("operations.import", "Импорт"),
        command=import_records_data,
    ).grid(row=0, column=4, sticky="ew", padx=(0, 6))
    ttk.Button(
        import_actions,
        text=tr("operations.export", "Экспорт"),
        command=export_records_data,
    ).grid(row=0, column=5, sticky="ew")

    context._refresh_list()

    type_combo.bind("<<ComboboxSelected>>", _on_type_change)
    _refresh_category_combo()

    return OperationsTabBindings(
        records_tree=records_tree,
        tags_tree=tags_tree,
        refresh_operation_wallet_menu=refresh_operation_wallet_menu,
        refresh_transfer_wallet_menus=refresh_transfer_wallet_menus,
        set_type_income=_set_type_income,
        set_type_expense=_set_type_expense,
        save_record=save_record,
        select_first=select_first_record,
        select_last=select_last_record,
        delete_selected=delete_selected,
        delete_all=delete_all,
        edit_selected=edit_selected_record_inline,
        inline_editor_active=inline_editor_active,
    )
