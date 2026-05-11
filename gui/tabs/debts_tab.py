"""Debts tab - debt and loan management."""

from __future__ import annotations

import logging
import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from tkinter import ttk
from typing import Any, Protocol

from domain.debt import Debt, DebtKind, DebtOperationType, DebtPayment
from domain.errors import DomainError
from gui.i18n import tr
from gui.logging_utils import log_ui_error
from gui.ui_dialogs import messagebox_compat as messagebox
from gui.ui_helpers import (
    attach_treeview_scrollbars,
    enable_treeview_column_autosize,
    parse_numeric_input,
)
from gui.ui_theme import (
    PAD_LG,
    PAD_SM,
    PAD_XL,
    PAD_XS,
    create_card_section,
    enable_treeview_zebra,
    get_palette,
)

logger = logging.getLogger(__name__)

_CONTROL_MASK = 0x0004
_SHIFT_MASK = 0x0001
_LOCAL_CTRL_ALIASES: dict[str, tuple[str, ...]] = {
    "p": ("p", "z", "cyrillic_ze", "з"),
    "w": ("w", "ts", "cyrillic_tse", "ц"),
}
_LOCAL_CTRL_KEYCODES: dict[str, int] = {
    "p": 80,
    "w": 87,
}


class DebtsTabContext(Protocol):
    controller: Any

    def _refresh_list(self) -> None: ...

    def _refresh_charts(self) -> None: ...

    def _refresh_wallets(self) -> None: ...

    def _refresh_all(self) -> None: ...


def refresh_debts_views(context: DebtsTabContext) -> None:
    for method_name in ("_refresh_list", "_refresh_charts", "_refresh_wallets", "_refresh_all"):
        method = getattr(context, method_name, None)
        if callable(method):
            method()


@dataclass(slots=True)
class DebtsTabBindings:
    debt_tree: ttk.Treeview
    history_tree: ttk.Treeview
    refresh: Callable[[], None]
    add_debt: Callable[[], None]
    pay_debt: Callable[[], None]
    write_off_debt: Callable[[], None]
    delete_debt: Callable[[], None]


def _segment_widths(*, total: int, bar_w: int, paid: int, forgiven: int) -> tuple[int, int, int]:
    total = max(int(total), 1)
    bar_w = max(int(bar_w), 1)
    paid = max(0, int(paid))
    forgiven = max(0, int(forgiven))

    paid_w = int(bar_w * paid / total) if paid > 0 else 0
    forgiven_w = int(bar_w * forgiven / total) if forgiven > 0 else 0

    if paid > 0 and paid_w == 0:
        paid_w = 1
    if forgiven > 0 and forgiven_w == 0:
        forgiven_w = 1

    overflow = max(0, paid_w + forgiven_w - bar_w)
    while overflow > 0 and (paid_w > 1 or forgiven_w > 1):
        if paid_w >= forgiven_w and paid_w > 1:
            paid_w -= 1
        elif forgiven_w > 1:
            forgiven_w -= 1
        overflow -= 1

    open_w = max(0, bar_w - paid_w - forgiven_w)
    return paid_w, forgiven_w, open_w


def _draw_debt_progress(
    canvas: tk.Canvas,
    debt: Debt | None,
    payments: list[DebtPayment],
    *,
    format_amount: Callable[[float], str] | None = None,
) -> None:
    palette = get_palette()
    canvas.delete("all")
    width = max(canvas.winfo_width(), 420)
    height = max(canvas.winfo_height(), 70)
    canvas.configure(
        height=height,
        bg=palette.surface_elevated,
        highlightbackground=palette.border_soft,
    )
    if debt is None or debt.total_amount_minor <= 0:
        canvas.create_text(
            width // 2,
            height // 2,
            text=tr("debts.progress.empty", "Выберите долг, чтобы увидеть прогресс"),
            fill=palette.text_muted,
            font=("Segoe UI", 10),
        )
        return

    total = max(1, int(debt.total_amount_minor))
    remaining = int(debt.remaining_amount_minor)
    forgiven = sum(
        int(payment.principal_paid_minor)
        for payment in payments
        if payment.operation_type is DebtOperationType.DEBT_FORGIVE
    )
    paid = max(0, total - remaining - forgiven)
    paid = max(0, min(total, paid))
    forgiven = max(0, min(total - paid, forgiven))
    open_amount = max(0, total - paid - forgiven)

    x0 = 20
    y0 = 18
    bar_w = max(120, width - 40)
    bar_h = 22
    debt_color = palette.warning if debt.kind is DebtKind.DEBT else palette.accent_blue
    forgive_color = palette.text_muted
    track_color = palette.surface_alt
    paid_w, forgiven_w, open_w = _segment_widths(
        total=total,
        bar_w=bar_w,
        paid=paid,
        forgiven=forgiven,
    )

    canvas.create_rectangle(x0, y0, x0 + bar_w, y0 + bar_h, fill=track_color, outline="")
    current_x = x0
    for seg_w, amount, color, is_open_segment in (
        (paid_w, paid, debt_color, False),
        (forgiven_w, forgiven, forgive_color, False),
        (open_w, open_amount, palette.surface_elevated, True),
    ):
        if amount <= 0 or seg_w <= 0:
            continue
        if is_open_segment:
            canvas.create_rectangle(
                current_x,
                y0,
                x0 + bar_w,
                y0 + bar_h,
                fill=color,
                outline="",
            )
        else:
            canvas.create_rectangle(
                current_x,
                y0,
                current_x + seg_w,
                y0 + bar_h,
                fill=color,
                outline="",
            )
            current_x += seg_w

    canvas.create_rectangle(x0, y0, x0 + bar_w, y0 + bar_h, outline=palette.border_soft, width=1)
    canvas.create_text(
        x0,
        y0 + bar_h + 14,
        anchor="w",
        text=tr(
            "debts.progress.summary",
            "Погашено: {paid}   Списано: {forgiven}   Осталось: {remaining}",
            paid=(format_amount or (lambda value: f"{value:.2f}"))(paid / 100),
            forgiven=(format_amount or (lambda value: f"{value:.2f}"))(forgiven / 100),
            remaining=(format_amount or (lambda value: f"{value:.2f}"))(remaining / 100),
        ),
        fill=palette.chart_text,
        font=("Segoe UI", 9),
    )


def build_debts_tab(
    parent: tk.Frame | ttk.Frame,
    *,
    context: DebtsTabContext,
) -> DebtsTabBindings:
    def format_display_amount(amount: float, precision: int = 2) -> str:
        return context.controller.format_display_amount(amount, precision=precision)

    def _base_currency_code() -> str:
        getter = getattr(context.controller, "get_base_currency_code", None)
        if callable(getter):
            return str(getter() or "").strip().upper() or "KZT"
        return "KZT"

    def _bind_control_shortcuts(widget: tk.Misc, handlers: dict[str, Callable[[], None]]) -> None:
        def _dispatch(event: tk.Event) -> str | None:
            state = int(getattr(event, "state", 0))
            if not state & _CONTROL_MASK or state & _SHIFT_MASK:
                return None
            keysym = str(getattr(event, "keysym", "") or "").strip().lower()
            char = str(getattr(event, "char", "") or "").strip().lower()
            keycode = getattr(event, "keycode", None)
            for letter, action in handlers.items():
                aliases = _LOCAL_CTRL_ALIASES.get(letter, (letter,))
                if (
                    keysym in aliases
                    or char in aliases
                    or keycode == _LOCAL_CTRL_KEYCODES.get(letter)
                ):
                    action()
                    return "break"
            return None

        widget.bind("<Control-KeyPress>", _dispatch, add="+")

    def _bind_focus_navigation(widgets: list[tk.Misc]) -> None:
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
                    "<KP_Enter>",
                    lambda _event: (_event.widget.invoke(), "break")[1],
                    add="+",
                )
            else:
                widget.bind("<Return>", lambda _event: "break", add="+")
                widget.bind("<KP_Enter>", lambda _event: "break", add="+")

    def _bind_submit_navigation(widgets: list[tk.Misc], action: Callable[[], None]) -> None:
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
                    "<KP_Enter>",
                    lambda _event: (_event.widget.invoke(), "break")[1],
                    add="+",
                )
            else:
                widget.bind("<Return>", lambda _event: (action(), "break")[1], add="+")
                widget.bind("<KP_Enter>", lambda _event: (action(), "break")[1], add="+")

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

    create_card = create_card_section(left, tr("debts.create.title", "Новый долг / заем"))
    create_card.grid(row=0, column=0, sticky="ew")
    create_frame = create_card.winfo_children()[-1]
    create_frame.grid_columnconfigure(1, weight=1)

    ttk.Label(create_frame, text=tr("common.type", "Тип:")).grid(
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

    ttk.Label(create_frame, text=tr("debts.contact", "Контакт:")).grid(
        row=1, column=0, sticky="w", padx=PAD_SM, pady=PAD_XS
    )
    contact_entry = ttk.Entry(create_frame)
    contact_entry.grid(row=1, column=1, sticky="ew", padx=PAD_SM, pady=PAD_XS)

    ttk.Label(create_frame, text=tr("debts.amount", "Сумма (валюта базы):")).grid(
        row=2, column=0, sticky="w", padx=PAD_SM, pady=PAD_XS
    )
    amount_entry = ttk.Entry(create_frame)
    amount_entry.grid(row=2, column=1, sticky="ew", padx=PAD_SM, pady=PAD_XS)

    ttk.Label(create_frame, text=tr("common.date", "Дата:")).grid(
        row=3, column=0, sticky="w", padx=PAD_SM, pady=PAD_XS
    )
    date_entry = ttk.Entry(create_frame)
    date_entry.grid(row=3, column=1, sticky="ew", padx=PAD_SM, pady=PAD_XS)
    date_entry.insert(0, date.today().isoformat())

    ttk.Label(create_frame, text=tr("common.wallet", "Кошелек:")).grid(
        row=4, column=0, sticky="w", padx=PAD_SM, pady=PAD_XS
    )
    wallet_var = tk.StringVar(value="")
    wallet_menu = ttk.Combobox(
        create_frame,
        textvariable=wallet_var,
        values=[],
        state="readonly",
    )
    wallet_menu.grid(row=4, column=1, sticky="ew", padx=PAD_SM, pady=PAD_XS)
    wallet_map: dict[str, int] = {}

    ttk.Label(create_frame, text=tr("common.description", "Описание:")).grid(
        row=5, column=0, sticky="w", padx=PAD_SM, pady=PAD_XS
    )
    description_entry = ttk.Entry(create_frame)
    description_entry.grid(row=5, column=1, sticky="ew", padx=PAD_SM, pady=PAD_XS)

    actions_card = create_card_section(
        left, tr("debts.actions.title", "Действия по выбранному долгу")
    )
    actions_card.grid(row=1, column=0, sticky="ew", pady=(PAD_LG, 0))
    actions_frame = actions_card.winfo_children()[-1]
    actions_frame.grid_columnconfigure(1, weight=1)

    ttk.Label(actions_frame, text=tr("debts.amount", "Сумма (валюта базы):")).grid(
        row=0, column=0, sticky="w", padx=PAD_SM, pady=PAD_XS
    )
    action_amount_entry = ttk.Entry(actions_frame)
    action_amount_entry.grid(row=0, column=1, sticky="ew", padx=PAD_SM, pady=PAD_XS)

    ttk.Label(actions_frame, text=tr("common.date", "Дата:")).grid(
        row=1, column=0, sticky="w", padx=PAD_SM, pady=PAD_XS
    )
    action_date_entry = ttk.Entry(actions_frame)
    action_date_entry.grid(row=1, column=1, sticky="ew", padx=PAD_SM, pady=PAD_XS)
    action_date_entry.insert(0, date.today().isoformat())

    ttk.Label(actions_frame, text=tr("common.wallet", "Кошелек:")).grid(
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

    debt_tree = ttk.Treeview(
        right,
        show="headings",
        columns=("id", "contact", "kind", "total", "remaining", "status", "created"),
        height=10,
    )
    enable_treeview_zebra(debt_tree)
    for col, label, width, anchor in (
        ("id", "#", 45, "e"),
        ("contact", tr("debts.contact_short", "Контакт"), 140, "w"),
        ("kind", tr("common.type_short", "Тип"), 80, "center"),
        ("total", tr("debts.total", "Сумма"), 125, "e"),
        ("remaining", tr("debts.remaining", "Остаток"), 140, "e"),
        ("status", tr("common.status", "Статус"), 85, "center"),
        ("created", tr("debts.created", "Создан"), 95, "center"),
    ):
        debt_tree.heading(col, text=label)
        debt_tree.column(col, width=width, minwidth=width, anchor=anchor, stretch=col == "contact")  # type: ignore[arg-type]
    enable_treeview_column_autosize(debt_tree, columns=("contact",), max_width=320)
    debt_tree.grid(row=0, column=0, sticky="nsew")
    attach_treeview_scrollbars(right, debt_tree, row=0, column=0, horizontal=True)

    progress_canvas = tk.Canvas(
        right,
        height=72,
        bg=palette.surface_elevated,
        highlightthickness=0,
        highlightbackground=palette.border_soft,
    )
    progress_canvas.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(8, 8))

    current_debt: Debt | None = None
    current_payments: list[DebtPayment] = []

    def _redraw_progress_on_resize(event=None):
        """Перерисовать прогрессбар при изменении размера canvas."""
        if current_debt is not None:
            _draw_debt_progress(
                progress_canvas,
                current_debt,
                current_payments,
                format_amount=lambda value: format_display_amount(value, precision=2),
            )
        else:
            _draw_debt_progress(progress_canvas, None, [], format_amount=None)

    progress_canvas.bind("<Configure>", _redraw_progress_on_resize)

    history_card = create_card_section(right, tr("common.history", "История"))
    history_card.grid(row=3, column=0, columnspan=2, sticky="nsew")
    history_frame = history_card.winfo_children()[-1]
    history_frame.grid_columnconfigure(0, weight=1)
    history_frame.grid_rowconfigure(0, weight=1)

    history_tree = ttk.Treeview(
        history_frame,
        show="headings",
        columns=("date", "operation", "amount", "write_off", "record"),
        height=8,
    )
    enable_treeview_zebra(history_tree)
    for col, label, width, anchor in (
        ("date", tr("common.date", "Дата"), 95, "center"),
        ("operation", tr("common.operation", "Операция"), 100, "w"),
        ("amount", tr("common.amount", "Сумма"), 125, "e"),
        ("write_off", tr("debts.write_off_short", "Списание"), 100, "center"),
        ("record", tr("debts.record_id", "ID записи"), 100, "center"),
    ):
        history_tree.heading(col, text=label)
        history_tree.column(
            col,
            width=width,
            minwidth=width,
            anchor=anchor,  # type: ignore[arg-type]
            stretch=col == "operation",
        )
    enable_treeview_column_autosize(history_tree, columns=("operation",), max_width=320)
    history_tree.grid(row=0, column=0, sticky="nsew")
    attach_treeview_scrollbars(history_frame, history_tree, row=0, column=0, horizontal=True)
    history_tree.tag_configure("writeoff", foreground=palette.text_muted)

    status_label = ttk.Label(left, text="")
    status_label.grid(row=2, column=0, sticky="w", pady=(8, 0))

    def _refresh_wallets() -> None:
        nonlocal wallet_map
        wallets = context.controller.load_active_wallets()
        wallet_map = {
            f"[{wallet.id}] {wallet.name} ({wallet.currency})": wallet.id for wallet in wallets
        }
        labels = list(wallet_map.keys()) or [""]
        for combo_widget, var in (
            (wallet_menu, wallet_var),
            (action_wallet_menu, action_wallet_var),
        ):
            combo_widget["values"] = labels
            if var.get() not in wallet_map:
                var.set(labels[0])

    def _selected_debt() -> Debt | None:
        selection = debt_tree.selection()
        if not selection:
            return None
        debt_id = int(selection[0])
        return next(
            (item for item in context.controller.get_debts() if int(item.id) == debt_id), None
        )

    def _refresh_history() -> None:
        nonlocal current_debt, current_payments
        history_tree.delete(*history_tree.get_children())
        debt = _selected_debt()
        if debt is None:
            current_debt = None
            current_payments = []
            _draw_debt_progress(progress_canvas, None, [], format_amount=None)
            return
        history = context.controller.get_debt_history(debt.id)
        current_debt = debt
        current_payments = history
        for payment in history:
            tag = ("writeoff",) if payment.is_write_off else ()
            history_tree.insert(
                "",
                "end",
                values=(
                    payment.payment_date,
                    payment.operation_type.value,
                    format_display_amount(payment.principal_paid_minor / 100, precision=2),
                    tr("common.yes", "Да") if payment.is_write_off else tr("common.no", "Нет"),
                    "" if payment.record_id is None else str(payment.record_id),
                ),
                tags=tag,
            )
        progress_canvas.after(
            20,
            lambda: _draw_debt_progress(
                progress_canvas,
                debt,
                history,
                format_amount=lambda value: format_display_amount(value, precision=2),
            ),
        )

    def _refresh() -> None:
        _refresh_wallets()
        debts = context.controller.get_debts()
        current_selection = debt_tree.selection()
        debt_tree.delete(*debt_tree.get_children())
        debt_tree.heading(
            "total",
            text=f"{tr('debts.total', 'Сумма')} ({context.controller.get_display_currency_code()})",
        )
        debt_tree.heading(
            "remaining",
            text=(
                f"{tr('debts.remaining', 'Остаток')} "
                f"({context.controller.get_display_currency_code()})"
            ),
        )
        history_tree.heading(
            "amount",
            text=(
                f"{tr('common.amount', 'Сумма')} ({context.controller.get_display_currency_code()})"
            ),
        )

        def _display_kind(kind: DebtKind) -> str:
            return {
                DebtKind.DEBT: tr("debts.kind.debt", "Долг"),
                DebtKind.LOAN: tr("debts.kind.loan", "Заем"),
            }.get(kind, str(kind.value))

        def _display_status(status: Any) -> str:
            raw = str(getattr(status, "value", status))
            return {
                "open": tr("debts.status.open", "Открыт"),
                "closed": tr("debts.status.closed", "Закрыт"),
            }.get(raw, raw)

        for debt in debts:
            debt_tree.insert(
                "",
                "end",
                iid=str(debt.id),
                values=(
                    debt.id,
                    debt.contact_name,
                    _display_kind(debt.kind),
                    format_display_amount(debt.total_amount_minor / 100, precision=2),
                    format_display_amount(debt.remaining_amount_minor / 100, precision=2),
                    _display_status(debt.status),
                    debt.created_at,
                ),
            )
        if current_selection and debt_tree.exists(current_selection[0]):
            debt_tree.selection_set(current_selection[0])
        elif debts:
            debt_tree.selection_set(str(debts[0].id))
        status_label.config(
            text=tr(
                "debts.status.summary",
                "{open_count} открыто / {total_count} всего",
                open_count=len(context.controller.get_open_debts()),
                total_count=len(debts),
            )
        )
        _refresh_history()

    def _create() -> None:
        contact = contact_entry.get().strip()
        date_text = date_entry.get().strip()
        description = description_entry.get().strip()
        wallet_id = wallet_map.get(wallet_var.get())
        try:
            amount_base = parse_numeric_input(amount_entry.get().strip())
        except ValueError:
            messagebox.showerror(
                tr("common.error", "Ошибка"),
                tr("debts.error.amount_number", "Сумма должна быть числом."),
            )
            return
        if wallet_id is None:
            messagebox.showerror(
                tr("common.error", "Ошибка"),
                tr("debts.error.wallet_required", "Кошелек обязателен."),
            )
            return
        if not contact:
            messagebox.showerror(
                tr("common.error", "Ошибка"),
                tr("debts.error.contact_required", "Контакт обязателен."),
            )
            return

        kind = DebtKind.DEBT if kind_var.get() == debt_label else DebtKind.LOAN
        try:
            if kind is DebtKind.DEBT:
                context.controller.create_debt(
                    contact_name=contact,
                    wallet_id=wallet_id,
                    amount_base=amount_base,
                    created_at=date_text,
                    currency=_base_currency_code(),
                    description=description,
                )
            else:
                context.controller.create_loan(
                    contact_name=contact,
                    wallet_id=wallet_id,
                    amount_base=amount_base,
                    created_at=date_text,
                    currency=_base_currency_code(),
                    description=description,
                )
            contact_entry.delete(0, tk.END)
            amount_entry.delete(0, tk.END)
            description_entry.delete(0, tk.END)
            _refresh()
            refresh_debts_views(context)
        except (DomainError, ValueError, TypeError, RuntimeError) as error:
            log_ui_error(
                logger,
                "UI_DEBTS_CREATE_FAILED",
                error,
                wallet_id=wallet_id,
                kind=kind.value,
            )
            messagebox.showerror(tr("debts.error.create_title", "Ошибка долга"), str(error))

    create_widgets = [
        kind_combo,
        contact_entry,
        amount_entry,
        date_entry,
        wallet_menu,
        description_entry,
    ]

    def _run_on_selected(
        self_name: str,
        action: Callable[[Debt, float, str, int | None], None],
        *,
        wallet_optional: bool = False,
    ) -> None:
        debt = _selected_debt()
        if debt is None:
            messagebox.showerror(
                tr("common.error", "Ошибка"),
                tr("debts.error.select_first", "Сначала выберите долг."),
            )
            return
        date_text = action_date_entry.get().strip()
        try:
            amount_base = parse_numeric_input(action_amount_entry.get().strip())
        except ValueError:
            messagebox.showerror(
                tr("common.error", "Ошибка"),
                tr("debts.error.amount_number", "Сумма должна быть числом."),
            )
            return
        wallet_id = wallet_map.get(action_wallet_var.get())
        if not wallet_optional and wallet_id is None:
            messagebox.showerror(
                tr("common.error", "Ошибка"),
                tr("debts.error.wallet_required", "Кошелек обязателен."),
            )
            return
        wallet_id_arg: int | None = wallet_id
        if not wallet_optional and wallet_id_arg is not None:
            wallet_id_arg = int(wallet_id_arg)
        try:
            action(debt, amount_base, date_text, wallet_id_arg)
            _refresh()
        except (DomainError, ValueError, TypeError, RuntimeError) as error:
            log_ui_error(
                logger,
                "UI_DEBTS_ACTION_FAILED",
                error,
                debt_id=debt.id,
                wallet_id=wallet_id_arg,
            )
            messagebox.showerror(self_name, str(error))

    def _pay() -> None:
        _run_on_selected(
            tr("debts.error.payment_title", "Ошибка погашения"),
            lambda debt, amount, date_text, wallet_id: context.controller.register_debt_payment(
                debt_id=debt.id,
                wallet_id=int(wallet_id),  # type: ignore[arg-type]
                amount_base=amount,
                payment_date=date_text,
            ),
        )
        refresh_debts_views(context)

    def _write_off() -> None:
        _run_on_selected(
            tr("debts.error.writeoff_title", "Ошибка списания"),
            lambda debt, amount, date_text, _wallet_id: context.controller.register_debt_write_off(
                debt_id=debt.id,
                amount_base=amount,
                payment_date=date_text,
            ),
            wallet_optional=True,
        )

    def _close() -> None:
        debt = _selected_debt()
        if debt is None:
            messagebox.showerror(
                tr("common.error", "Ошибка"),
                tr("debts.error.select_first", "Сначала выберите долг."),
            )
            return
        if debt.remaining_amount_minor <= 0:
            messagebox.showerror(
                tr("common.error", "Ошибка"),
                tr("debts.error.already_closed", "Долг уже закрыт."),
            )
            return
        wallet_id = wallet_map.get(action_wallet_var.get())
        if wallet_id is None and debt.kind is DebtKind.DEBT:
            messagebox.showerror(
                tr("common.error", "Ошибка"),
                tr("debts.error.wallet_required", "Кошелек обязателен."),
            )
            return
        try:
            context.controller.close_debt(
                debt_id=debt.id,
                payment_date=action_date_entry.get().strip(),
                wallet_id=wallet_id,
                write_off=False,
            )
            _refresh()
            refresh_debts_views(context)
        except (DomainError, ValueError, TypeError, RuntimeError) as error:
            log_ui_error(logger, "UI_DEBTS_CLOSE_FAILED", error, debt_id=debt.id)
            messagebox.showerror(tr("debts.error.close_title", "Ошибка закрытия"), str(error))

    def _delete() -> None:
        debt = _selected_debt()
        if debt is None:
            messagebox.showerror(
                tr("common.error", "Ошибка"),
                tr("debts.error.select_first", "Сначала выберите долг."),
            )
            return
        if not messagebox.askyesno(
            tr("common.confirm", "Подтверждение"),
            tr(
                "debts.confirm.delete",
                "Удалить долг для '{contact}'?\n"
                "\nЭто удалит только карточку долга и историю платежей."
                "\nСвязанные записи доходов/расходов и балансы кошельков останутся без изменений.",
                contact=debt.contact_name,
            ),
        ):
            return
        try:
            context.controller.delete_debt(debt.id)
            _refresh()
        except (DomainError, ValueError, TypeError, RuntimeError) as error:
            log_ui_error(logger, "UI_DEBTS_DELETE_FAILED", error, debt_id=debt.id)
            messagebox.showerror(tr("debts.error.delete_title", "Ошибка удаления"), str(error))

    create_button = ttk.Button(
        create_frame,
        text=tr("debts.save", "Сохранить"),
        style="Primary.TButton",
        command=_create,
    )
    create_button.grid(row=6, column=0, columnspan=2, sticky="ew", padx=6, pady=8)
    _bind_submit_navigation([*create_widgets, create_button], _create)
    pay_button = ttk.Button(actions_frame, text=tr("debts.pay", "Погасить"), command=_pay)
    pay_button.grid(row=3, column=0, sticky="ew", padx=6, pady=6)
    write_off_button = ttk.Button(
        actions_frame, text=tr("debts.write_off", "Списать"), command=_write_off
    )
    write_off_button.grid(row=3, column=1, sticky="ew", padx=6, pady=6)
    close_button = ttk.Button(actions_frame, text=tr("debts.close", "Закрыть"), command=_close)
    close_button.grid(row=4, column=0, sticky="ew", padx=6, pady=(0, 6))
    delete_button = ttk.Button(actions_frame, text=tr("debts.delete", "Удалить"), command=_delete)
    delete_button.grid(row=4, column=1, sticky="ew", padx=6, pady=(0, 6))
    refresh_button = ttk.Button(
        actions_frame, text=tr("common.refresh", "Обновить"), command=_refresh
    )
    refresh_button.grid(row=5, column=0, columnspan=2, sticky="ew", padx=6, pady=(0, 6))

    action_navigation_widgets: list[tk.Misc] = [
        action_amount_entry,
        action_date_entry,
        action_wallet_menu,
        pay_button,
        write_off_button,
        close_button,
        delete_button,
        refresh_button,
    ]
    _bind_focus_navigation(action_navigation_widgets)

    for widget in action_navigation_widgets:
        _bind_control_shortcuts(widget, {"p": _pay, "w": _write_off})

    debt_tree.bind("<<TreeviewSelect>>", lambda _event: _refresh_history(), add="+")
    _refresh()
    return DebtsTabBindings(
        debt_tree=debt_tree,
        history_tree=history_tree,
        refresh=_refresh,
        add_debt=_create,
        pay_debt=_pay,
        write_off_debt=_write_off,
        delete_debt=_delete,
    )
