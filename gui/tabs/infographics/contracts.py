"""Public contracts for the infographics tab."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass
from tkinter import ttk
from typing import Literal, Protocol

from domain.records import Record


@dataclass(slots=True)
class InfographicsTabBindings:
    pie_month_var: tk.StringVar
    pie_month_menu: ttk.Combobox
    chart_month_var: tk.StringVar
    chart_month_menu: ttk.Combobox
    chart_year_var: tk.StringVar
    chart_year_menu: ttk.Combobox
    expense_pie_canvas: tk.Canvas
    expense_legend_canvas: tk.Canvas
    expense_legend_frame: tk.Frame
    daily_bar_canvas: tk.Canvas
    monthly_bar_canvas: tk.Canvas


class InfographicsRepository(Protocol):
    def load_all(self) -> list[Record]: ...


class InfographicsController(Protocol):
    def format_display_money(
        self,
        amount_base: float,
        *,
        precision: int = 2,
        with_code: bool = True,
    ) -> str: ...


class InfographicsChartsOwner(Protocol):
    chart_month_menu: ttk.Combobox | None
    chart_month_var: tk.StringVar | None
    pie_month_menu: ttk.Combobox | None
    pie_month_var: tk.StringVar | None
    chart_year_menu: ttk.Combobox | None
    chart_year_var: tk.StringVar | None
    expense_pie_canvas: tk.Canvas | None
    expense_legend_canvas: tk.Canvas | None
    expense_legend_frame: tk.Frame | None
    daily_bar_canvas: tk.Canvas | None
    monthly_bar_canvas: tk.Canvas | None
    _chart_refresh_suspended: bool


class InfographicsRefreshOwner(InfographicsChartsOwner, Protocol):
    _infographics_records_cache: list[object] | None

    @property
    def repository(self) -> InfographicsRepository: ...

    @property
    def controller(self) -> InfographicsController: ...


class ScrollOwner(Protocol):
    expense_legend_canvas: tk.Canvas | None

    def winfo_containing(
        self,
        rootX: int,
        rootY: int,
        displayof: tk.Misc | Literal[0] | None = 0,
    ) -> tk.Misc | None: ...


class MouseWheelEventLike(Protocol):
    x_root: int
    y_root: int
    delta: int


class ComboLike(Protocol):
    def __setitem__(self, key: str, value: object) -> None: ...


class StringVarLike(Protocol):
    def get(self) -> str: ...

    def set(self, value: str) -> None: ...


class AfterLike(Protocol):
    def __call__(self, delay_ms: int, callback: Callable[[], None]) -> str: ...
