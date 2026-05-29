from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass
from tkinter import ttk
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class AnalyticsSnapshotController(Protocol):
    def get_period_snapshot(
        self,
        start_date: str,
        end_date: str,
        *,
        category_limit: int | None = None,
        tag_limit: int | None = None,
    ) -> Any: ...

    def get_refresh_snapshot(
        self,
        start_date: str,
        end_date: str,
        *,
        category_limit: int | None = None,
        tag_limit: int | None = None,
    ) -> Any: ...


class AnalyticsController(Protocol):
    def get_total_balance(self, date: str | None = None) -> float: ...

    def get_savings_rate(self, start_date: str, end_date: str) -> float: ...

    def get_burn_rate(self, start_date: str, end_date: str) -> float: ...

    def get_average_monthly_income(self, year: int, *, up_to_date: str | None = None) -> float: ...

    def get_year_income(self, year: int, *, up_to_date: str | None = None) -> float: ...

    def convert_base_to_usd(self, amount_base: float) -> float: ...

    def get_year_expense(self, year: int, *, up_to_date: str | None = None) -> float: ...

    def get_average_monthly_expenses(self, start_date: str, end_date: str) -> float: ...

    def get_time_costs(self, start_date: str, end_date: str) -> tuple[float, float, float]: ...

    def get_net_worth_timeline(self) -> list[Any]: ...

    def get_spending_by_category(
        self,
        start_date: str,
        end_date: str,
        *,
        limit: int | None = None,
    ) -> list[Any]: ...

    def get_income_by_category(
        self,
        start_date: str,
        end_date: str,
        *,
        limit: int | None = None,
    ) -> list[Any]: ...

    def get_spending_by_tag(
        self,
        start_date: str,
        end_date: str,
        *,
        limit: int | None = None,
    ) -> list[Any]: ...

    def get_monthly_summary(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[Any]: ...


class AnalyticsTabContext(Protocol):
    @property
    def controller(self) -> AnalyticsController: ...

    def after(self, ms: int, func: Callable[[], None]) -> str: ...

    def after_cancel(self, id: str) -> None: ...


@dataclass(slots=True)
class AnalyticsTabBindings:
    period_from_entry: ttk.Entry
    period_to_entry: ttk.Entry
    net_worth_label: ttk.Label
    savings_rate_label: ttk.Label
    burn_rate_label: ttk.Label
    spending_tree: ttk.Treeview
    income_tree: ttk.Treeview
    category_canvas: tk.Canvas
    monthly_tree: ttk.Treeview
    timeline_canvas: tk.Canvas
    refresh: Callable[[], None]
    toggle_tag_mode: Callable[[], None]
