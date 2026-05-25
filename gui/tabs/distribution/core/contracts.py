from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass
from tkinter import ttk
from typing import Any, Protocol


class DistributionController(Protocol):
    def create_distribution_item(self, name: str, *, group_name: str, pct: float) -> None: ...

    def create_distribution_subitem(self, item_id: int, name: str, *, pct: float) -> None: ...

    def update_distribution_item_pct(self, item_id: int, pct: float) -> None: ...

    def update_distribution_subitem_pct(self, subitem_id: int, pct: float) -> None: ...

    def update_distribution_item_name(self, item_id: int, new_name: str) -> None: ...

    def update_distribution_subitem_name(self, subitem_id: int, new_name: str) -> None: ...

    def delete_distribution_item(self, item_id: int) -> None: ...

    def delete_distribution_subitem(self, subitem_id: int) -> None: ...

    def toggle_distribution_month_fixed(self, month: str) -> None: ...

    def format_display_amount(self, amount: float, *, precision: int = 0) -> str: ...

    def get_display_currency_code(self) -> str: ...

    def get_distribution_subitems(self, item_id: int) -> list[Any]: ...

    def is_distribution_month_auto_fixed(self, month: str) -> bool: ...

    def is_distribution_month_fixed(self, month: str) -> bool: ...

    def get_distribution_items(self) -> list[Any]: ...

    def get_distribution_history(self, start_month: str, end_month: str) -> list[Any]: ...

    def get_frozen_distribution_rows(
        self,
        start_month: str | None = None,
        end_month: str | None = None,
    ) -> list[Any]: ...

    def validate_distribution(self) -> list[str]: ...


class DistributionTabContext(Protocol):
    controller: DistributionController


@dataclass(slots=True)
class DistributionTabBindings:
    structure_tree: ttk.Treeview
    validation_label: ttk.Label
    period_from_var: tk.StringVar
    period_to_var: tk.StringVar
    results_tree: ttk.Treeview
    status_label: ttk.Label
    refresh: Callable[[], None]
