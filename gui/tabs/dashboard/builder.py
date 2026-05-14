"""Dashboard tab builder."""

from __future__ import annotations

import logging
import tkinter as tk
from tkinter import ttk

from domain.dashboard import DashboardPayload
from domain.errors import DomainError
from domain.goal import GoalProgress
from gui.i18n import tr
from gui.logging_utils import log_ui_error
from gui.ui_helpers import ask_confirm, bind_label_wrap, show_error
from gui.ui_theme import PAD_SM, PAD_XL, create_card_section, get_palette

from .contracts import DashboardTabBindings, DashboardTabContext
from .dialogs import (
    show_asset_editor_dialog,
    show_bulk_asset_snapshot_dialog,
    show_create_goal_dialog,
    show_manage_assets_dialog,
)
from .render import _draw_allocation, _draw_trend, _render_goals_with_actions

logger = logging.getLogger(__name__)


def build_dashboard_tab(
    parent: tk.Frame | ttk.Frame,
    *,
    context: DashboardTabContext,
) -> DashboardTabBindings:
    palette = get_palette()

    def display_code() -> str:
        getter = getattr(context.controller, "get_display_currency_code", None)
        if callable(getter):
            return str(getter() or "").strip().upper() or "KZT"
        getter = getattr(context.controller, "get_display_currency", None)
        if callable(getter):
            return str(getter() or "").strip().upper() or "KZT"
        return "KZT"

    def format_display_amount(amount: float, precision: int = 0) -> str:
        formatter = getattr(context.controller, "format_display_amount", None)
        if callable(formatter):
            return str(formatter(amount, precision=precision))
        return f"{float(amount):,.{precision}f}"

    def format_display_money(amount: float, precision: int = 0) -> str:
        formatter = getattr(context.controller, "format_display_money", None)
        if callable(formatter):
            return str(formatter(amount, precision=precision))
        return f"{format_display_amount(amount, precision=precision)} {display_code()}"

    parent.grid_columnconfigure(0, weight=1)
    parent.grid_rowconfigure(1, weight=1)

    toolbar = ttk.Frame(parent)
    toolbar.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 6))
    toolbar.grid_columnconfigure(0, weight=1)

    ttk.Label(
        toolbar,
        text=tr("dashboard.title", "Дашборд активов и целей"),
        font=("Segoe UI", 12, "bold"),
    ).grid(row=0, column=0, sticky="w")
    action_row = ttk.Frame(toolbar)
    action_row.grid(row=1, column=0, sticky="ew", pady=(8, 0))
    ttk.Label(
        action_row,
        text=tr("dashboard.quick_actions", "Быстрые действия:"),
        foreground=palette.text_muted,
    ).pack(side=tk.LEFT)
    create_asset_button = ttk.Button(
        action_row,
        text=tr("dashboard.create_asset", "Создать актив"),
        style="Primary.TButton",
    )
    create_asset_button.pack(side=tk.LEFT, padx=(12, 8))
    manage_assets_button = ttk.Button(
        action_row,
        text=tr("dashboard.manage_assets", "Управление активами"),
    )
    manage_assets_button.pack(side=tk.LEFT, padx=(0, 8))
    create_goal_button = ttk.Button(action_row, text=tr("dashboard.create_goal", "Создать цель"))
    create_goal_button.pack(side=tk.LEFT, padx=(0, 8))
    bulk_update_button = ttk.Button(
        action_row,
        text=tr("dashboard.bulk_update", "Обновить активы"),
    )
    bulk_update_button.pack(side=tk.LEFT, padx=(0, 8))
    refresh_button = ttk.Button(action_row, text=tr("common.refresh", "Обновить"))
    refresh_button.pack(side=tk.LEFT)

    paned = ttk.PanedWindow(parent, orient=tk.VERTICAL)
    paned.grid(row=1, column=0, sticky="nsew", padx=PAD_XL, pady=(0, PAD_SM))

    summary_card = create_card_section(paned, tr("dashboard.overview", "Обзор"))
    paned.add(summary_card, weight=1)
    summary_frame = summary_card.winfo_children()[-1]
    for column in range(3):
        summary_frame.grid_columnconfigure(column, weight=1)
    summary_frame.grid_rowconfigure(4, weight=1)

    net_worth_label = ttk.Label(
        summary_frame,
        text=tr("dashboard.net_worth", "Чистый капитал: {amount}", amount="-"),
        font=("Segoe UI", 14, "bold"),
        style="CardText.TLabel",
    )
    net_worth_label.grid(row=0, column=0, sticky="w", padx=12, pady=(12, 4))

    assets_total_label = ttk.Label(
        summary_frame,
        text=tr("dashboard.assets_total", "Активы всего: {amount}", amount="-"),
        font=("Segoe UI", 14, "bold"),
        style="CardText.TLabel",
    )
    assets_total_label.grid(row=0, column=1, sticky="w", padx=12, pady=(12, 4))

    goals_status_label = ttk.Label(
        summary_frame,
        text=tr(
            "dashboard.goals_status",
            "Цели: {completed} / {total} завершено",
            completed="-",
            total="-",
        ),
        font=("Segoe UI", 14, "bold"),
        style="CardText.TLabel",
    )
    goals_status_label.grid(row=0, column=2, sticky="w", padx=12, pady=(12, 4))

    assets_status_label = ttk.Label(
        summary_frame,
        text=tr(
            "dashboard.assets_status",
            "Активы: {active} активных / {total} всего",
            active="-",
            total="-",
        ),
        foreground=palette.text_muted,
        style="CardSubtle.TLabel",
    )
    assets_status_label.grid(row=1, column=0, sticky="w", padx=12, pady=(0, 4))

    trend_label = ttk.Label(
        summary_frame,
        text=tr("dashboard.trend.title", "Динамика капитала"),
        font=("Segoe UI", 10, "bold"),
        style="CardText.TLabel",
    )
    trend_label.grid(row=2, column=0, columnspan=2, sticky="w", padx=12, pady=(8, 0))
    ttk.Label(
        summary_frame,
        text=tr("dashboard.trend.hint", "Краткая помесячная динамика капитала."),
        foreground=palette.text_muted,
        style="CardSubtle.TLabel",
    ).grid(row=3, column=0, columnspan=2, sticky="w", padx=12)

    allocation_label = ttk.Label(
        summary_frame,
        text=tr("dashboard.allocation.title", "Структура активов"),
        font=("Segoe UI", 10, "bold"),
        style="CardText.TLabel",
    )
    allocation_label.grid(row=2, column=2, sticky="w", padx=12, pady=(8, 0))
    ttk.Label(
        summary_frame,
        text=tr(
            "dashboard.allocation.hint",
            "Активные активы, сгруппированные по категориям.",
        ),
        foreground=palette.text_muted,
        style="CardSubtle.TLabel",
    ).grid(row=3, column=2, sticky="w", padx=12)

    trend_canvas = tk.Canvas(summary_frame, bg=palette.surface_elevated, highlightthickness=0)
    trend_canvas.grid(row=4, column=0, columnspan=2, sticky="nsew", padx=(12, 6), pady=(6, 12))

    allocation_canvas = tk.Canvas(
        summary_frame,
        bg=palette.surface_elevated,
        highlightthickness=0,
    )
    allocation_canvas.grid(row=4, column=2, sticky="nsew", padx=(6, 12), pady=(6, 12))

    goals_card = create_card_section(paned, tr("dashboard.goals.title", "Цели"))
    paned.add(goals_card, weight=1)
    goals_frame = goals_card.winfo_children()[-1]
    goals_frame.grid_columnconfigure(0, weight=1)
    goals_frame.grid_rowconfigure(1, weight=1)

    goals_header = ttk.Frame(goals_frame)
    goals_header.grid(row=0, column=0, columnspan=2, sticky="ew", padx=10, pady=(10, 0))
    goals_header.grid_columnconfigure(0, weight=1)
    goals_hint_label = ttk.Label(
        goals_header,
        text=tr(
            "dashboard.goals.hint",
            "Следите за прогрессом и меняйте статус целей прямо отсюда.",
        ),
        style="CardSubtle.TLabel",
        foreground=palette.text_muted,
    )
    goals_hint_label.grid(row=0, column=0, sticky="ew")
    bind_label_wrap(goals_hint_label, goals_header, max_width=720)

    goals_canvas = tk.Canvas(goals_frame, bg=palette.surface_elevated, highlightthickness=0)
    goals_canvas.grid(row=1, column=0, sticky="nsew", padx=(10, 0), pady=10)

    goals_scroll = ttk.Scrollbar(goals_frame, orient="vertical", command=goals_canvas.yview)
    goals_scroll.grid(row=1, column=1, sticky="ns", padx=(6, 10), pady=10)
    goals_canvas.configure(yscrollcommand=goals_scroll.set)

    goals_inner = ttk.Frame(goals_canvas)
    goals_window = goals_canvas.create_window((0, 0), window=goals_inner, anchor="nw")

    last_payload: DashboardPayload | None = None
    redraw_job: str | None = None

    def _sync_goals_scrollregion(_event: tk.Event | None = None) -> None:
        goals_canvas.configure(scrollregion=goals_canvas.bbox("all"))

    def _resize_goals_window(_event: tk.Event) -> None:
        goals_canvas.itemconfigure(goals_window, width=_event.width)

    def _schedule_redraw() -> None:
        nonlocal redraw_job
        if redraw_job is not None:
            try:
                context.after_cancel(redraw_job)
            except (tk.TclError, RuntimeError):
                pass
        redraw_job = context.after(120, _redraw)

    def _redraw() -> None:
        nonlocal redraw_job
        redraw_job = None
        if last_payload is None:
            _draw_trend(
                trend_canvas,
                [],
                format_amount=lambda value: format_display_amount(value, precision=0),
            )
            _draw_allocation(
                allocation_canvas,
                [],
                format_money=lambda value: format_display_money(value, precision=0),
            )
            return
        _draw_trend(
            trend_canvas,
            list(last_payload.trend),
            format_amount=lambda value: format_display_amount(value, precision=0),
        )
        _draw_allocation(
            allocation_canvas,
            list(last_payload.allocation),
            format_money=lambda value: format_display_money(value, precision=0),
        )

    def _refresh() -> None:
        nonlocal last_payload
        try:
            payload = context.controller.get_dashboard_payload()
            last_payload = payload
            all_assets = list(context.controller.get_assets(active_only=False))
            active_assets = [asset for asset in all_assets if bool(asset.is_active)]
            net_worth_label.config(
                text=tr(
                    "dashboard.net_worth",
                    "Чистый капитал: {amount}",
                    amount=format_display_money(payload.summary.net_worth_base, precision=0),
                )
            )
            assets_total_label.config(
                text=tr(
                    "dashboard.assets_total",
                    "Активы всего: {amount}",
                    amount=format_display_money(payload.summary.assets_total_base, precision=0),
                )
            )
            goals_status_label.config(
                text=tr(
                    "dashboard.goals_status",
                    "Цели: {completed} / {total} завершено",
                    completed=payload.summary.goals_completed,
                    total=payload.summary.goals_total,
                )
            )
            assets_status_label.config(
                text=tr(
                    "dashboard.assets_status",
                    "Активы: {active} активных / {total} всего",
                    active=len(active_assets),
                    total=len(all_assets),
                )
            )
            _render_goals_with_actions(
                goals_inner,
                list(payload.goals),
                on_toggle_completed=_toggle_goal_completed,
                on_delete_goal=_delete_goal,
            )
            _sync_goals_scrollregion()
            _redraw()
        except (DomainError, ValueError, TypeError, RuntimeError) as error:
            log_ui_error(logger, "UI_DASH_REFRESH_FAILED", error)
            show_error(str(error), title="Ошибка дашборда")

    def _toggle_goal_completed(goal_progress: GoalProgress) -> None:
        goal = goal_progress.goal
        completed = not bool(goal_progress.is_completed)
        try:
            context.controller.set_goal_completed(goal.id, completed)
        except (DomainError, ValueError, TypeError, RuntimeError) as error:
            log_ui_error(logger, "UI_DASH_GOAL_TOGGLE_FAILED", error, goal_id=goal.id)
            show_error(str(error), title="Ошибка обновления цели", parent=parent)
            return
        _refresh()

    def _delete_goal(goal_progress: GoalProgress) -> None:
        goal = goal_progress.goal
        confirmed = ask_confirm(
            tr("dashboard.goal.delete.confirm", "Удалить цель '{title}'?", title=goal.title),
            title=tr("common.confirm", "Подтверждение"),
            parent=parent,
        )
        if not confirmed:
            return
        try:
            context.controller.delete_goal(goal.id)
        except (DomainError, ValueError, TypeError, RuntimeError) as error:
            log_ui_error(logger, "UI_DASH_GOAL_DELETE_FAILED", error, goal_id=goal.id)
            show_error(str(error), title="Ошибка удаления цели", parent=parent)
            return
        _refresh()

    def _open_bulk_update_dialog() -> None:
        show_bulk_asset_snapshot_dialog(parent, context=context, on_saved=_refresh)

    def _open_create_goal_dialog() -> None:
        show_create_goal_dialog(parent, context=context, on_saved=_refresh)

    def _open_create_asset_dialog() -> None:
        show_asset_editor_dialog(parent, context=context, initial_asset=None, on_saved=_refresh)

    def _open_manage_assets_dialog() -> None:
        show_manage_assets_dialog(parent, context=context, on_saved=_refresh)

    create_asset_button.configure(command=_open_create_asset_dialog)
    manage_assets_button.configure(command=_open_manage_assets_dialog)
    create_goal_button.configure(command=_open_create_goal_dialog)
    bulk_update_button.configure(command=_open_bulk_update_dialog)
    refresh_button.configure(command=_refresh)
    trend_canvas.bind("<Configure>", lambda _event: _schedule_redraw())
    allocation_canvas.bind("<Configure>", lambda _event: _schedule_redraw())
    goals_canvas.bind("<Configure>", _resize_goals_window)
    goals_inner.bind("<Configure>", _sync_goals_scrollregion)

    _refresh()

    return DashboardTabBindings(
        net_worth_label=net_worth_label,
        assets_total_label=assets_total_label,
        goals_status_label=goals_status_label,
        assets_status_label=assets_status_label,
        trend_canvas=trend_canvas,
        allocation_canvas=allocation_canvas,
        goals_canvas=goals_canvas,
        create_asset_button=create_asset_button,
        manage_assets_button=manage_assets_button,
        create_goal_button=create_goal_button,
        bulk_update_button=bulk_update_button,
        refresh=_refresh,
    )
