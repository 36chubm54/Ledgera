from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass
from tkinter import ttk
from typing import Protocol

from domain.budget import Budget, BudgetResult


class BudgetController(Protocol):
    def get_display_currency_code(self) -> str: ...

    def format_display_amount(self, amount: float, *, precision: int = 0) -> str: ...

    def format_display_money(self, amount: float, *, precision: int = 0) -> str: ...

    def list_tags(self) -> list[object]: ...

    def get_expense_categories(self) -> list[str]: ...

    def get_mandatory_expense_categories(self) -> list[str]: ...

    def get_budget_results(self) -> list[BudgetResult]: ...

    def get_budgets(self) -> list[Budget]: ...

    def create_budget(
        self,
        *,
        category: str,
        start_date: str,
        end_date: str,
        limit_base: float,
        include_mandatory: bool,
        scope_type: str,
        scope_value: str,
    ) -> None: ...

    def delete_budget(self, budget_id: int) -> None: ...

    def update_budget_limit(self, budget_id: int, limit_base: float) -> None: ...


class BudgetTabContext(Protocol):
    controller: BudgetController

    def _refresh_charts(self) -> None: ...


@dataclass(slots=True)
class BudgetTabBindings:
    category_combo: ttk.Combobox
    start_date_entry: ttk.Entry
    end_date_entry: ttk.Entry
    limit_entry: ttk.Entry
    include_mandatory_var: tk.BooleanVar
    budget_tree: ttk.Treeview
    progress_canvas: tk.Canvas
    status_label: ttk.Label
    refresh: Callable[[], None]
    add_budget: Callable[[], None]
    edit_budget: Callable[[], None]
    delete_budget: Callable[[], None]
